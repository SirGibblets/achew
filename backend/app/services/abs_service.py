import asyncio
import base64
import logging
import math
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from ..core.config import get_app_config
from ..models.abs import (
    AudnexusChapterList,
    Book,
    LibrarySearchHit,
    LibrarySearchResponse,
    MatchType,
)
from .audible_providers import (
    all_regions,
    region_for_language,
    region_for_provider,
)

logger = logging.getLogger(__name__)

# How many author / series / narrator matches a single search expands into books.
# Each costs one extra request.
MAX_GROUPS_PER_TYPE = 3

# How many books to pull per expanded collection. Sized to swallow whole
# catalogues in one request so the UI can page through them without re-running
# this fan-out: a busy author/narrator can credit over a hundred books. Anything
# past this is still counted in the reported total, just not returned.
GROUP_EXPANSION_LIMIT = 250

_library_cache: Dict[str, Dict] = {}
_library_provider_cache: Dict[str, Optional[str]] = {}


def _parse_books(items: List[Any]) -> List[Book]:
    """Parse raw ABS library items into books, keeping only those with audio.

    Expanded items report their audio as an `audioFiles` list while minified ones
    (library listings and `filter=` queries) only carry a `numAudioFiles` count, so
    both have to be consulted. One unparseable item never fails the whole batch.
    """
    books: List[Book] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        media = item.get("media") or {}
        if not (media.get("numAudioFiles") or media.get("audioFiles")):
            continue
        try:
            books.append(Book(**item))
        except Exception as e:
            logger.warning(f"Failed to parse book data: {e}")
    return books


def _series_sequence(book: Book) -> float:
    """Numeric reading position of a book within its series.

    Sequences are free text in ABS: "3", "8.5" and "1-2" (an omnibus) all occur,
    so the leading number is what orders them. Unnumbered entries are usually
    companion volumes and sort after the numbered ones.
    """
    series = book.media.metadata.series
    raw = series[0].sequence if series else None
    if not raw:
        return math.inf
    match = re.match(r"\s*(\d+(?:\.\d+)?)", raw)
    return float(match.group(1)) if match else math.inf


def _apply_series_order(entries: List[Tuple[Book, MatchType, str]]) -> List[Tuple[Book, MatchType, str]]:
    """Put each series into reading order without disturbing anything else.

    Whatever ranked these already — Audiobookshelf's own relevance for direct
    title hits, title order for an expanded author — decides where a series
    first appears, and the whole series then follows from that position in
    sequence order. Sorting the list outright by series would instead throw away
    that ranking, and leaving it alone returns a series scattered out of order.
    """
    # A book with no series is its own group, which pins it where it already is.
    first_seen: Dict[str, int] = {}
    for index, (book, _, _) in enumerate(entries):
        series = book.media.metadata.series
        key = series[0].name if series else f"\0{index}"
        first_seen.setdefault(key, index)

    def sort_key(item: Tuple[int, Tuple[Book, MatchType, str]]) -> Tuple[int, float]:
        index, (book, _, _) = item
        series = book.media.metadata.series
        key = series[0].name if series else f"\0{index}"
        return first_seen[key], _series_sequence(book)

    # Python's sort is stable, so equal sequences keep their incoming order.
    return [entry for _, entry in sorted(enumerate(entries), key=sort_key)]


class ABSService:
    """Service for interacting with Audiobookshelf API"""

    def __init__(self):
        self.config = get_app_config().abs
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("ABSService must be used as an async context manager")
        return self._session

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    def _get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"}

    async def health_check(self) -> bool:
        """Check if ABS server is accessible"""
        try:
            url = f"{self.config.url}/ping"
            headers = self._get_headers()
            logger.info(f"Health check URL: {url}")

            # Create a fresh session for health check
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    logger.info(f"Health check response status: {resp.status}")
                    if resp.status != 200:
                        response_text = await resp.text()
                        logger.error(f"Health check failed with status {resp.status}, response: {response_text}")
                    return resp.status == 200
        except Exception as e:
            logger.error(f"ABS health check failed: {e}", exc_info=True)
            return False

    async def get_book_details(self, book_id: str) -> Optional[Book]:
        """Fetch detailed book information from ABS"""
        try:
            url = f"{self.config.url}/api/items/{book_id}"
            async with self.session.get(url, headers=self._get_headers()) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return Book(**data)
                else:
                    logger.error(f"Failed to fetch book details for {book_id}: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching book details for {book_id}: {e}")
            return None

    async def get_audnexus_chapters(self, asin: str, region: str = "US") -> Optional[AudnexusChapterList]:
        """Fetch chapters from Audnexus for a given ASIN"""
        try:
            url = f"{self.config.url}/api/search/chapters"
            params = {"asin": asin, "region": region}
            async with self.session.get(url, headers=self._get_headers(), params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("stringKey") == "MessageChaptersNotFound":
                        logger.info(f"No chapters found for ASIN:{asin} in {region} region")
                        return None
                    if "error" in data:
                        logger.error(f"Failed to fetch Audnexus chapters: {data.get('error')}")
                        return None
                    return AudnexusChapterList(**data)
                else:
                    logger.error(f"Failed to fetch Audnexus chapters: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching Audnexus chapters: {e}")
            return None

    async def get_library_provider(self, library_id: str) -> Optional[str]:
        global _library_provider_cache
        if library_id in _library_provider_cache:
            return _library_provider_cache[library_id]

        provider: Optional[str] = None
        try:
            url = f"{self.config.url}/api/libraries/{library_id}"
            async with self.session.get(url, headers=self._get_headers()) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    raw = data.get("provider")
                    if isinstance(raw, str) and raw:
                        provider = raw
                else:
                    logger.warning(f"Failed to fetch library {library_id}: {resp.status}")
        except Exception as e:
            logger.warning(f"Error fetching library {library_id}: {e}")

        _library_provider_cache[library_id] = provider
        return provider

    async def find_audnexus_chapters(self, book: Book) -> Optional[AudnexusChapterList]:
        """
        Try Audnexus across multiple regions in priority order:
        1. The library's audible provider (if any).
        2. The audible region matching the book's metadata language (if any).
        3. All remaining regions; pick the result with the closest duration.
        """
        asin = book.media.metadata.asin
        if not asin:
            return None

        tried: set[str] = set()

        if book.libraryId:
            lib_provider = await self.get_library_provider(book.libraryId)
            region = region_for_provider(lib_provider)
            if region:
                result = await self.get_audnexus_chapters(asin, region=region)
                tried.add(region)
                if result:
                    return result

        lang_region = region_for_language(book.media.metadata.language)
        if lang_region and lang_region not in tried:
            result = await self.get_audnexus_chapters(asin, region=lang_region)
            tried.add(lang_region)
            if result:
                return result

        remaining = [r for r in all_regions() if r not in tried]
        if not remaining:
            return None

        results = await asyncio.gather(*(self.get_audnexus_chapters(asin, region=r) for r in remaining))
        candidates = [r for r in results if r is not None]
        if not candidates:
            return None

        book_ms = (book.duration or 0) * 1000
        return min(candidates, key=lambda c: abs(c.runtimeLengthMs - book_ms))

    async def download_audio_file(
        self,
        book_id: str,
        audio_file_ino: str,
        output_path: str,
        progress_callback=None,
        cancellation_check=None,
    ) -> bool:
        """Download audio file with progress tracking and cancellation support"""
        try:
            url = f"{self.config.url}/api/items/{book_id}/file/{audio_file_ino}/download"

            async with self.session.get(url, headers=self._get_headers()) as resp:
                resp.raise_for_status()
                total_size = int(resp.headers.get("Content-Length", 0))
                chunk_size = 1024 * 1024  # 1 MB chunks
                downloaded = 0
                last_callback_time = 0.0

                with open(output_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        # Check for cancellation before writing each chunk
                        if cancellation_check and cancellation_check():
                            logger.info("Download cancelled during chunk processing")
                            # Remove partial file
                            try:
                                f.close()
                                if os.path.exists(output_path):
                                    os.remove(output_path)
                            except Exception:
                                pass
                            return False

                        f.write(chunk)
                        downloaded += len(chunk)

                        if progress_callback:
                            current_time = time.time()
                            # Only call progress_callback once every 0.1 seconds
                            if current_time - last_callback_time >= 0.1:
                                progress_callback(downloaded, total_size)
                                last_callback_time = current_time

                # Ensure final progress update is sent
                if progress_callback:
                    progress_callback(downloaded, total_size)
                return True
        except asyncio.CancelledError:
            logger.info("Download was cancelled")
            # Remove partial file
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except Exception:
                pass
            return False
        except Exception as e:
            logger.error(f"Error downloading audio file: {e}")
            return False

    async def download_file(self, book_id: str, ino: str, output_path: str) -> bool:
        """Download a library file (non-audio) from ABS"""
        try:
            url = f"{self.config.url}/api/items/{book_id}/file/{ino}/download"
            async with self.session.get(url, headers=self._get_headers()) as resp:
                resp.raise_for_status()
                with open(output_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 256):
                        f.write(chunk)
                return True
        except Exception as e:
            logger.error(f"Error downloading library file (ino={ino}): {e}")
            return False

    async def search_books(
        self,
        provider: str,
        title: str = "",
        author: str = "",
        book_id: str = "",
    ) -> List:
        """Search for books via the ABS /api/search/books endpoint.

        Returns a list of BookSearchResult objects.
        """
        from ..models.abs import BookSearchResult

        try:
            url = f"{self.config.url}/audiobookshelf/api/search/books"
            params: Dict[str, str] = {"provider": provider, "fallbackTitleOnly": "1"}
            if title:
                params["title"] = title
            if author:
                params["author"] = author
            if book_id:
                params["id"] = book_id

            async with self.session.get(url, headers=self._get_headers(), params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []
                    for item in data:
                        try:
                            results.append(BookSearchResult(**item))
                        except Exception as e:
                            logger.warning(f"Could not parse book search result: {e}")
                    return results
                else:
                    logger.error(f"Book search failed: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Error searching books: {e}")
            return []

    async def upload_chapters(
        self,
        book_id: str,
        chapters: List[Tuple[float, str]],
        duration: float,
    ) -> bool:
        """Upload processed chapters back to ABS"""
        try:
            url = f"{self.config.url}/api/items/{book_id}/chapters"
            headers = {
                **self._get_headers(),
                "Content-Type": "application/json",
            }

            # Format chapters with start/end times
            formatted_chapters = []
            for i, (timestamp, title) in enumerate(chapters):
                chapter = {
                    "id": i,
                    "start": 0 if i == 0 else timestamp,
                    "end": duration if i == len(chapters) - 1 else chapters[i + 1][0],
                    "title": title,
                }
                formatted_chapters.append(chapter)

            payload = {"chapters": formatted_chapters}

            async with self.session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    return True
                else:
                    error_details = await resp.text()
                    logger.error(f"Failed to update chapters: {resp.status}, response: {error_details}")
                    return False

        except Exception as e:
            logger.error(f"Error uploading chapters: {e}")
            return False

    async def get_libraries(self) -> List[Dict]:
        """Fetch libraries filtered for book media type"""
        try:
            url = f"{self.config.url}/api/libraries"
            async with self.session.get(url, headers=self._get_headers()) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Filter for book libraries only
                    book_libraries = []
                    if "libraries" in data:
                        for library in data["libraries"]:
                            if library.get("mediaType") == "book":
                                book_libraries.append(
                                    {
                                        "id": library["id"],
                                        "name": library["name"],
                                        "mediaType": library["mediaType"],
                                    }
                                )
                    return book_libraries
                else:
                    logger.error(f"Failed to fetch libraries: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching libraries: {e}")
            return []

    async def _get_filtered_library_items(
        self,
        library_id: str,
        filter_key: str,
        filter_value: str,
        limit: int,
    ) -> Tuple[List[Book], int]:
        """Fetch library items matching one of ABS's `filter=<key>.<base64 value>` queries.

        Authors and series filter on an id; narrators, tags and genres filter on a name,
        since ABS models those as bare strings.

        Returns the parsed books alongside the collection's full size as ABS reports
        it, which is independent of `limit`. A prolific author/narrator can outrun any cap
        worth fetching, and the caller needs the real size to say how much is hidden.
        """
        try:
            encoded = base64.b64encode(filter_value.encode()).decode()
            url = f"{self.config.url}/api/libraries/{library_id}/items"
            params = {"filter": f"{filter_key}.{encoded}", "limit": limit}
            async with self.session.get(url, headers=self._get_headers(), params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch {filter_key} items for library {library_id}: {resp.status}")
                    return [], 0
                data = await resp.json()
                results = data.get("results", [])
                return _parse_books(results), data.get("total", len(results))
        except Exception as e:
            logger.error(f"Error fetching {filter_key} items for library {library_id}: {e}")
            return [], 0

    async def search_library(self, library_id: str, query: str, limit: int = 12) -> LibrarySearchResponse:
        """Search a library by title, subtitle, series, author or narrator.

        ABS's search endpoint returns matches grouped by what they matched, but only
        the `book` group carries library items; author, series and narrator matches
        name a collection that has to be expanded into its books separately. Results
        are de-duplicated across the groups and ordered by `MatchType`.
        """
        try:
            url = f"{self.config.url}/api/libraries/{library_id}/search"
            params = {"q": query, "limit": limit}
            async with self.session.get(url, headers=self._get_headers(), params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to search library {library_id}: {resp.status}")
                    return LibrarySearchResponse(hits=[], total=0)
                data = await resp.json()
        except Exception as e:
            logger.error(f"Error searching library {library_id}: {e}")
            return LibrarySearchResponse(hits=[], total=0)

        # Direct book matches. ABS ranks these itself and does not say which field it
        # matched, so attribute each to its title or subtitle by inspecting the query.
        direct: List[Tuple[Book, MatchType, str]] = []
        for item in data.get("book") or []:
            library_item = item.get("libraryItem")
            if not isinstance(library_item, dict):
                continue
            for book in _parse_books([library_item]):
                metadata = book.media.metadata
                if metadata.subtitle and query.lower() in metadata.subtitle.lower():
                    if query.lower() not in metadata.title.lower():
                        direct.append((book, MatchType.SUBTITLE, metadata.subtitle))
                        continue
                direct.append((book, MatchType.TITLE, metadata.title))

        # Expand the collection matches concurrently — each is an independent request,
        # and a query can plausibly hit an author, a series and a narrator at once.
        groups = [
            (MatchType.SERIES, "series", entry.get("series", {}).get("id"), entry.get("series", {}).get("name"))
            for entry in (data.get("series") or [])[:MAX_GROUPS_PER_TYPE]
        ]
        groups += [
            (MatchType.AUTHOR, "authors", entry.get("id"), entry.get("name"))
            for entry in (data.get("authors") or [])[:MAX_GROUPS_PER_TYPE]
        ]
        # Narrator name is both the filter value and the label.
        groups += [
            (MatchType.NARRATOR, "narrators", entry.get("name"), entry.get("name"))
            for entry in (data.get("narrators") or [])[:MAX_GROUPS_PER_TYPE]
        ]
        groups = [g for g in groups if g[2] and g[3]]

        expanded: List[Tuple[List[Book], int]] = await asyncio.gather(
            *(
                self._get_filtered_library_items(library_id, key, value, GROUP_EXPANSION_LIMIT)
                for _, key, value, _ in groups
            )
        )

        buckets: Dict[MatchType, List[Tuple[Book, MatchType, str]]] = {
            MatchType.TITLE: [c for c in direct if c[1] == MatchType.TITLE],
            MatchType.SUBTITLE: [c for c in direct if c[1] == MatchType.SUBTITLE],
            MatchType.SERIES: [],
            MatchType.AUTHOR: [],
            MatchType.NARRATOR: [],
        }
        # Books a collection holds beyond GROUP_EXPANSION_LIMIT and so was never
        # fetched. Counting them keeps the reported total honest; they cannot be
        # de-duplicated against the other buckets, but being the tail of one
        # oversized collection they rarely overlap.
        unfetched = 0
        for (match_type, _, _, label), (books, group_total) in zip(groups, expanded):
            unfetched += max(0, group_total - len(books))
            if match_type != MatchType.SERIES:
                # ABS returns series-filtered items in sequence order already, which is
                # the useful order.
                books = sorted(books, key=lambda b: b.media.metadata.title.lower())
            buckets[match_type].extend((book, match_type, label) for book in books)

        # First bucket to claim a book wins, so each appears once under its strongest match.
        seen: set[str] = set()
        hits: List[LibrarySearchHit] = []
        for match_type in MatchType:
            for book, _, label in _apply_series_order(buckets[match_type]):
                if book.id in seen:
                    continue
                seen.add(book.id)
                hits.append(LibrarySearchHit(book=book, match_type=match_type, match_text=label))

        return LibrarySearchResponse(hits=hits[:limit], total=len(hits) + unfetched)

    async def get_library_items(self, library_id: str, use_cache: bool = True) -> List[Book]:
        """Fetch all items from the specified library"""
        global _library_cache

        if use_cache and library_id in _library_cache:
            cache_entry = _library_cache[library_id]
            logger.info(f"Using cached data for library {library_id}")
            return cache_entry["books"]

        try:
            url = f"{self.config.url}/api/libraries/{library_id}/items"
            params = {"sort": "addedAt", "desc": 1}

            async with self.session.get(url, headers=self._get_headers(), params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    books = _parse_books(data.get("results", []))
                    for book in books:
                        if book.media and book.media.coverPath:
                            book.media.coverPath = f"/api/audiobookshelf/covers/{book.id}"

                    _library_cache[library_id] = {"books": books, "timestamp": datetime.now()}

                    logger.info(f"Fetched and cached {len(books)} books from library {library_id}")
                    return books
                else:
                    logger.error(f"Failed to fetch library items from {library_id}: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching library items from {library_id}: {e}")
            return []

    @staticmethod
    def clear_library_cache(library_id: Optional[str] = None):
        """Clear cache for a specific library or all libraries"""
        global _library_cache, _library_provider_cache

        if library_id:
            if library_id in _library_cache:
                del _library_cache[library_id]
            _library_provider_cache.pop(library_id, None)
            logger.info(f"Cleared cache for library {library_id}")
        else:
            _library_cache.clear()
            _library_provider_cache.clear()
            logger.info("Cleared all library cache")
