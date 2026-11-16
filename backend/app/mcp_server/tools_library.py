"""MCP tools for the app as a whole and the Audiobookshelf library: status, finding books,
and auditing a library with Chapter Search."""

import asyncio
import importlib.metadata
import logging
import re
import time
import unicodedata
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ToolAnnotations
from pydantic import Field

from app.app import get_app_state
from app.core.config import get_app_config, is_abs_configured
from app.services.abs_service import ABSService
from app.services.asr_service_options import get_preferred_service
from app.services.chapter_search.database import delete_books_for_library
from app.services.chapter_search.rules.models import Rule, RuleSet
from app.services.chapter_search.rules.persistence import load_ruleset
from app.services.chapter_search.search import run_search
from app.services.chapter_search.sync import sync_library

from .runtime import (
    DEFAULT_WAIT_SECONDS,
    MAX_WAIT_SECONDS,
    READ_ONLY,
    fmt_duration,
    result,
    shutdown,
    snapshot,
    tool_errors,
    tools_revision,
)

logger = logging.getLogger(__name__)

READ_ONLY_REMOTE = ToolAnnotations(read_only_hint=True, open_world_hint=True)

# Chapter titles shown per matched book, enough to judge what's wrong with them
SAMPLE_TITLES = 6

# ABS matches search text literally, so "No Man's Land" misses "No Man’s Land". Queries are
# retried with quotes and dashes folded both ways and accents removed, then, failing that, with
# each of their FALLBACK_WORDS longest words (at least FALLBACK_MIN_WORD letters, up to
# FALLBACK_LIMIT hits), keeping the hits that contain the whole query once punctuation and
# accents are ignored. A word typed without its accent can't find the title, so several are tried.
_FOLD = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"})
FALLBACK_MIN_WORD = 3
FALLBACK_WORDS = 3
FALLBACK_LIMIT = 50


def _version() -> str:
    try:
        return importlib.metadata.version("achew")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _comparable(text: str) -> str:
    """Lowercase words only: no accents, quotes, dashes or other punctuation."""
    return " ".join(re.findall(r"\w+", _strip_accents(text.translate(_FOLD)).lower()))


def _query_variants(query: str) -> List[str]:
    straight = query.translate(_FOLD)
    plain = _strip_accents(straight)
    variants: List[str] = []
    for variant in [query, straight, straight.replace("'", "\u2019"), plain, plain.replace("'", "\u2019")]:
        if variant not in variants:
            variants.append(variant)
    return variants


async def _search_library(abs_service: ABSService, library_id: str, query: str, limit: int):
    """Search one library, tolerating quote/dash/accent differences. Returns the hits and the
    query that found them."""
    for variant in _query_variants(query):
        response = await abs_service.search_library(library_id, variant, limit)
        if response.hits:
            return response.hits, variant
    wanted = _comparable(query)
    words = sorted({w for w in re.findall(r"\w+", query) if len(w) >= FALLBACK_MIN_WORD}, key=len, reverse=True)
    for word in words[:FALLBACK_WORDS]:
        response = await abs_service.search_library(library_id, word, FALLBACK_LIMIT)
        hits = []
        for hit in response.hits:
            metadata = hit.book.media.metadata
            fields = [
                metadata.title,
                metadata.subtitle,
                metadata.authorName,
                metadata.seriesName,
                metadata.narratorName,
            ]
            if wanted in _comparable(" ".join(f for f in fields if f)):
                hits.append(hit)
        if hits:
            return hits[:limit], word
    return [], query


def _book_row(book, library_name: Optional[str] = None) -> Dict[str, Any]:
    metadata = book.media.metadata
    chapter_count = book.media.numChapters
    if chapter_count is None and book.media.chapters:
        chapter_count = len(book.media.chapters)
    return {
        "item_id": book.id,
        "title": metadata.title,
        "subtitle": metadata.subtitle,
        "author": metadata.authorName or None,
        "series": metadata.seriesName or None,
        "length": fmt_duration(book.duration) if book.duration else None,
        "chapters": chapter_count,
        "library": library_name,
    }


async def _list_library(library_id: Optional[str], offset: int, limit: int) -> CallToolResult:
    if not library_id:
        raise ToolError("Pass library_id to list a library's books (see list_libraries), or a query to search")
    async with ABSService() as abs_service:
        books = await abs_service.get_library_items(library_id)
    books = sorted(books, key=lambda b: _comparable(b.media.metadata.title))
    page = books[offset : offset + limit]
    return result(
        {
            "total": len(books),
            "offset": offset,
            "books": [_book_row(b) for b in page],
            "next_offset": offset + limit if offset + limit < len(books) else None,
        }
    )


def _require_abs() -> None:
    if not is_abs_configured():
        raise ToolError("Audiobookshelf isn't set up yet. The user needs to finish setup in Achew's web UI.")


# ---------------------------------------------------------------------------
# Chapter Search runs
# ---------------------------------------------------------------------------


class _LibraryScan:
    """A Chapter Search sync + search of one library, which outlives the tool call that started it."""

    def __init__(self, library_id: str):
        self.library_id = library_id
        self.phase = "sync"
        self.current = 0
        self.total = 0
        self.results: Optional[List[dict]] = None
        self.error: Optional[str] = None
        self.finished_at: Optional[float] = None
        self.task: Optional[asyncio.Task] = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    async def run(self) -> None:
        cancel = asyncio.Event()

        def progress(phase: str, current: int, total: int) -> None:
            self.phase, self.current, self.total = phase, current, total

        try:
            await sync_library(self.library_id, progress, cancel)
            self.phase = "search"
            self.results = await run_search(self.library_id, load_ruleset(), progress, cancel)
        except Exception as e:
            logger.error(f"Chapter Search for MCP failed: {e}", exc_info=True)
            self.error = str(e) or type(e).__name__
        finally:
            self.finished_at = time.time()


# Results stay fresh for this long; later calls with the same library reuse them
SCAN_RESULT_TTL_SECONDS = 15 * 60

_scans: Dict[str, _LibraryScan] = {}


def _rule_names(ruleset: RuleSet) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for item in ruleset.items:
        if isinstance(item, Rule):
            names[item.id] = item.display_name()
        else:
            names.update(_rule_names(item))
    return names


def _enabled_rules(ruleset: RuleSet) -> List[str]:
    if not ruleset.enabled:
        return []
    found: List[str] = []
    for item in ruleset.items:
        if isinstance(item, Rule):
            if item.enabled:
                found.append(item.display_name())
        else:
            found.extend(_enabled_rules(item))
    return found


def register(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_status() -> CallToolResult:
        """Where Achew is right now: whether it's set up, the open book (if any), its step, and what to do
        next. Call this first. The session is shared with Achew's web UI, so the user may be working in it too."""
        app_state = get_app_state()
        config = get_app_config()
        preferred = get_preferred_service()
        return result(
            {
                "achew_version": _version(),
                # Compare with the revision in the instructions you got when you connected
                "tools_revision": tools_revision(),
                "audiobookshelf_configured": is_abs_configured(),
                "transcription_service": preferred.name if preferred else None,
                "agents_can_submit": config.mcp.allow_submit,
                # The AI Cleanup custom instructions the user turned on, which say how they like titles
                "title_preferences": [i.text for i in config.custom_instructions.instructions if i.checked and i.text]
                or "none set: choose one consistent style yourself",
                "session": snapshot(app_state),
            }
        )

    @server.tool(annotations=READ_ONLY_REMOTE)
    @tool_errors
    async def list_libraries() -> CallToolResult:
        """List the Audiobookshelf book libraries (id and name)."""
        _require_abs()
        async with ABSService() as abs_service:
            libraries = await abs_service.get_libraries()
        return result({"libraries": [{"id": lib["id"], "name": lib["name"]} for lib in libraries]})

    @server.tool(annotations=READ_ONLY_REMOTE)
    @tool_errors
    async def search_books(
        query: Annotated[
            Optional[str],
            Field(description="Title, subtitle, series, author or narrator to search for; omit to list a library"),
        ] = None,
        library_id: Annotated[
            Optional[str], Field(description="Library to search (omit to search all), or to list without a query")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=100, description="Maximum results (per library, when searching)")] = 10,
        offset: Annotated[int, Field(ge=0, description="When listing a library: skip this many books")] = 0,
    ) -> CallToolResult:
        """Find books in Audiobookshelf. Returns each book's item id (what open_book takes), its length, and how
        many chapters it currently has. Curly vs straight quotes, dashes and accents don't need to match.
        Without a query, lists a library's books by title (pass library_id; page with offset)."""
        _require_abs()
        if query is None or not query.strip():
            return await _list_library(library_id, offset, limit)
        if len(query.strip()) < 2:
            raise ToolError("The search query needs at least 2 characters")

        async with ABSService() as abs_service:
            libraries = await abs_service.get_libraries()
            if library_id:
                libraries = [lib for lib in libraries if lib["id"] == library_id]
                if not libraries:
                    raise ToolError(f"No book library with id {library_id!r}; see list_libraries")
            responses = await asyncio.gather(
                *(_search_library(abs_service, lib["id"], query.strip(), limit) for lib in libraries)
            )

        books: List[Dict[str, Any]] = []
        searched_as = {variant for hits, variant in responses if hits and variant != query.strip()}
        for library, (hits, _) in zip(libraries, responses):
            for hit in hits:
                books.append({**_book_row(hit.book, library["name"]), "matched_on": hit.match_type.value})
        return result({"books": books, "searched_as": sorted(searched_as) or None})

    @server.tool(annotations=READ_ONLY_REMOTE)
    @tool_errors
    async def find_books_needing_cleanup(
        library_id: Annotated[str, Field(description="Library to audit (see list_libraries)")],
        ctx: Context,
        offset: Annotated[int, Field(ge=0, description="Skip this many matches (for paging)")] = 0,
        limit: Annotated[int, Field(ge=1, le=100, description="Matches to return")] = 25,
        include_ignored: Annotated[bool, Field(description="Include books the user marked as ignored")] = False,
        refresh: Annotated[
            bool,
            Field(description="Re-download every book's chapters first (after chapters were edited outside Achew)"),
        ] = False,
        timeout_seconds: Annotated[float, Field(ge=0, le=MAX_WAIT_SECONDS)] = DEFAULT_WAIT_SECONDS,
    ) -> CallToolResult:
        """Audit a library with Chapter Search: list books whose chapters match the user's saved Chapter Search
        rules (by default: fewer than 4 chapters, mostly number-only titles, or titles repeating the book title).

        The first run downloads every book's chapter list, which can take minutes on a big library. If it isn't
        done within timeout_seconds the result has `busy: true`; call again with the same library_id to keep
        waiting. Results are reused for 15 minutes, so paging with offset is cheap."""
        _require_abs()

        scan = _scans.get(library_id)
        stale = (
            scan is not None
            and not scan.running
            and (scan.error is not None or time.time() - (scan.finished_at or 0) > SCAN_RESULT_TTL_SECONDS)
        )
        if scan is None or stale or (refresh and not scan.running):
            if refresh:
                await delete_books_for_library(library_id)
            scan = _LibraryScan(library_id)
            scan.task = asyncio.create_task(scan.run())
            _scans[library_id] = scan

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while scan.running and loop.time() < deadline and not shutdown.started:
            try:
                await ctx.report_progress(float(scan.current), float(scan.total or 1), f"{scan.phase}")
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if scan.running:
            return result(
                {
                    "busy": True,
                    "working_on": f"{scan.phase} {scan.current}/{scan.total}",
                    "next": "Call find_books_needing_cleanup again with the same library_id to keep waiting.",
                }
            )
        if scan.error is not None:
            raise ToolError(f"Chapter Search failed: {scan.error}")

        ruleset = load_ruleset()
        names = _rule_names(ruleset)
        matches = [b for b in scan.results or [] if include_ignored or not b.get("is_ignored")]
        page = matches[offset : offset + limit]
        books = []
        for book in page:
            chapters = book.get("chapters") or []
            books.append(
                {
                    "item_id": book["id"],
                    "title": book["name"],
                    "author": book.get("author"),
                    "series": book.get("series"),
                    "length": fmt_duration(book["duration"]) if book.get("duration") else None,
                    "chapters": len(chapters),
                    "matched_rules": [names.get(rule_id, rule_id) for rule_id in book.get("matched_rule_ids", [])],
                    "sample_titles": [c["title"] for c in chapters[:SAMPLE_TITLES]],
                    "ignored": book.get("is_ignored") or None,
                }
            )
        return result(
            {
                "rules": _enabled_rules(ruleset),
                "matched": len(matches),
                "offset": offset,
                "books": books,
                "next_offset": offset + limit if offset + limit < len(matches) else None,
            }
        )
