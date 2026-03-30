"""ChapterSearchState singleton — manages WebSocket connections and search state."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket

from ...services.abs_service import ABSService
from .database import delete_books_for_library, set_ignore
from .rules.models import RuleSet
from .rules.evaluator import evaluate_ruleset
from .rules.persistence import load_ruleset, save_ruleset
from .search import run_search
from .sync import sync_library, sync_specific_books

logger = logging.getLogger(__name__)


class ChapterSearchState:
    """
    Singleton that manages state for the Chapter Search feature.

    State is page-scoped and pushed to all connected WebSocket clients:
      landing   → {libraries, root_ruleset}
      searching → {current_task, progress}
      results   → {count, library_name, results}
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.page: str = "landing"
            self.selected_library_id: Optional[str] = None
            self.selected_library_name: Optional[str] = None
            self.results: Optional[list[dict]] = None
            self.current_task: Optional[str] = None
            self.progress: Optional[dict] = None
            self.stats: Optional[dict] = None
            self._ws_connections: list[WebSocket] = []
            self._cancel_event: Optional[asyncio.Event] = None
            self._active_task: Optional[asyncio.Task] = None
            ChapterSearchState._initialized = True

    # ------------------------------------------------------------------
    # WebSocket management
    # ------------------------------------------------------------------

    async def add_ws_connection(self, websocket: WebSocket) -> None:
        self._ws_connections.append(websocket)
        logger.info("Chapter search WebSocket connected")
        # Push full current state so the client lands on the right page
        await self._push_state_to(websocket)

    def remove_ws_connection(self, websocket: WebSocket) -> None:
        try:
            self._ws_connections.remove(websocket)
            logger.info("Chapter search WebSocket disconnected")
        except ValueError:
            pass

    async def broadcast_state(self) -> None:
        """Push the current page-scoped state to all connected clients."""
        payload = await self._build_state_payload()
        data = json.dumps(payload)
        dead = []
        for ws in list(self._ws_connections):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove_ws_connection(ws)

    async def _push_state_to(self, websocket: WebSocket) -> None:
        payload = await self._build_state_payload()
        try:
            await websocket.send_text(json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to push initial state to new client: {e}")

    async def _build_state_payload(self) -> dict:
        if self.page == "landing":
            libraries = await self._get_libraries()
            ruleset = load_ruleset()
            return {
                "page": "landing",
                "state": {
                    "libraries": libraries,
                    "root_ruleset": ruleset.model_dump(),
                },
            }
        elif self.page == "searching":
            return {
                "page": "searching",
                "state": {
                    "current_task": self.current_task,
                    "progress": self.progress,
                },
            }
        elif self.page == "stats":
            return {
                "page": "stats",
                "state": {
                    "stats": self.stats or {},
                    "library_name": self.selected_library_name,
                },
            }
        else:  # results
            ruleset = load_ruleset()
            return {
                "page": "results",
                "state": {
                    "count": len(self.results) if self.results else 0,
                    "library_name": self.selected_library_name,
                    "results": self.results or [],
                    "root_ruleset": ruleset.model_dump(),
                },
            }

    async def _get_libraries(self) -> list[dict]:
        try:
            async with ABSService() as abs_service:
                return await abs_service.get_libraries()
        except Exception as e:
            logger.error(f"Failed to fetch libraries: {e}")
            return []

    # ------------------------------------------------------------------
    # Incoming WebSocket message handler
    # ------------------------------------------------------------------

    async def handle_ws_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            logger.warning(f"Invalid JSON from chapter search WS: {raw!r}")
            return

        action = msg.get("action")
        if action == "start_search":
            library_id = msg.get("library_id")
            library_name = msg.get("library_name", library_id)
            if library_id:
                await self._start_search(library_id, library_name)
        elif action == "cancel":
            await self._cancel()
        elif action == "back_to_landing":
            await self._back_to_landing()
        elif action == "start_stats":
            library_id = msg.get("library_id")
            library_name = msg.get("library_name", library_id)
            if library_id:
                await self._start_stats(library_id, library_name)
        elif action == "refresh_results":
            await self._refresh_results()
        else:
            logger.warning(f"Unknown chapter search action: {action!r}")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _start_search(self, library_id: str, library_name: str) -> None:
        if self._active_task and not self._active_task.done():
            logger.warning("Chapter search already in progress, ignoring duplicate start")
            return

        self.selected_library_id = library_id
        self.selected_library_name = library_name
        self.page = "searching"
        self.current_task = "sync"
        self.progress = {"current": 0, "total": 0}
        self._cancel_event = asyncio.Event()

        await self.broadcast_state()

        self._active_task = asyncio.create_task(
            self._run_sync_and_search(library_id, library_name)
        )

    async def _run_sync_and_search(self, library_id: str, library_name: str) -> None:
        ruleset = load_ruleset()
        cancel = self._cancel_event

        def progress_cb(task: str, current: int, total: int) -> None:
            self.current_task = task
            self.progress = {"current": current, "total": total}
            asyncio.create_task(self.broadcast_state())

        try:
            # Sync phase
            synced, skipped = await sync_library(library_id, progress_cb, cancel)
            if cancel.is_set():
                await self._back_to_landing()
                return
            logger.info(f"Sync complete: {synced} synced, {skipped} skipped")

            # Search phase
            self.current_task = "search"
            self.progress = {"current": 0, "total": 0}
            await self.broadcast_state()

            results = await run_search(library_id, ruleset, progress_cb, cancel)
            if cancel.is_set():
                await self._back_to_landing()
                return

            self.results = results
            self.page = "results"
            await self.broadcast_state()

        except Exception as e:
            logger.error(f"Chapter search failed: {e}", exc_info=True)
            await self._back_to_landing()

    async def _start_stats(self, library_id: str, library_name: str) -> None:
        if self._active_task and not self._active_task.done():
            logger.warning("Chapter search already in progress, ignoring stats request")
            return

        self.selected_library_id = library_id
        self.selected_library_name = library_name
        self.page = "searching"
        self.current_task = "sync"
        self.progress = {"current": 0, "total": 0}
        self._cancel_event = asyncio.Event()

        await self.broadcast_state()

        self._active_task = asyncio.create_task(
            self._run_sync_and_stats(library_id)
        )

    async def _run_sync_and_stats(self, library_id: str) -> None:
        cancel = self._cancel_event

        def progress_cb(task: str, current: int, total: int) -> None:
            self.current_task = task
            self.progress = {"current": current, "total": total}
            asyncio.create_task(self.broadcast_state())

        try:
            synced, skipped = await sync_library(library_id, progress_cb, cancel)
            if cancel.is_set():
                await self._back_to_landing()
                return
            logger.info(f"Stats sync complete: {synced} synced, {skipped} skipped")

            self.current_task = "stats"
            self.progress = {"current": 0, "total": 0}
            await self.broadcast_state()

            from .stats import compute_library_stats
            self.stats = await compute_library_stats(library_id)
            self.page = "stats"
            await self.broadcast_state()

        except Exception as e:
            logger.error(f"Stats computation failed: {e}", exc_info=True)
            await self._back_to_landing()

    async def _cancel(self) -> None:
        if self._cancel_event:
            self._cancel_event.set()
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        await self._back_to_landing()

    async def _back_to_landing(self) -> None:
        self.page = "landing"
        self.results = None
        self.stats = None
        self.current_task = None
        self.progress = None
        await self.broadcast_state()

    async def _refresh_results(self) -> None:
        if not self.results or self.page != "results":
            return
        if self._active_task and not self._active_task.done():
            return

        book_ids = [b["id"] for b in self.results]
        self.page = "searching"
        self.current_task = "sync"
        self.progress = {"current": 0, "total": len(book_ids)}
        self._cancel_event = asyncio.Event()
        await self.broadcast_state()

        self._active_task = asyncio.create_task(self._run_refresh(book_ids))

    async def _run_refresh(self, book_ids: list[str]) -> None:
        ruleset = load_ruleset()
        cancel = self._cancel_event

        def progress_cb(task: str, current: int, total: int) -> None:
            self.current_task = task
            self.progress = {"current": current, "total": total}
            asyncio.create_task(self.broadcast_state())

        try:
            await sync_specific_books(self.selected_library_id, book_ids, progress_cb, cancel)
            if cancel.is_set():
                await self._back_to_landing()
                return

            self.current_task = "search"
            self.progress = {"current": 0, "total": 0}
            await self.broadcast_state()

            results = await run_search(self.selected_library_id, ruleset, progress_cb, cancel)
            if cancel.is_set():
                await self._back_to_landing()
                return

            self.results = results
            self.page = "results"
            await self.broadcast_state()

        except Exception as e:
            logger.error(f"Chapter search refresh failed: {e}", exc_info=True)
            self.page = "results"
            await self.broadcast_state()

    # ------------------------------------------------------------------
    # REST-callable methods
    # ------------------------------------------------------------------

    async def update_book_chapters(self, book_id: str, chapters: list[dict]) -> None:
        """Update chapters for a book in the in-memory results and re-evaluate rules.

        If the book no longer matches, it is removed from results.
        """
        if not self.results or self.page != "results":
            return
        ruleset = load_ruleset()
        for i, book in enumerate(self.results):
            if book["id"] == book_id:
                chapter_titles = [ch["title"] for ch in chapters]
                matched, matched_ids = evaluate_ruleset(ruleset, book["name"], chapter_titles)
                if matched:
                    book["chapters"] = chapters
                    book["matched_rule_ids"] = matched_ids
                else:
                    self.results.pop(i)
                await self.broadcast_state()
                break

    async def toggle_ignore(self, book_id: str) -> None:
        """Toggle the ignore status of a book and broadcast updated results."""
        if not self.results:
            return
        for book in self.results:
            if book["id"] == book_id:
                new_ignored = not book["is_ignored"]
                book["is_ignored"] = new_ignored
                await set_ignore(book_id, new_ignored)
                break
        await self.broadcast_state()

    async def clear_cache(self, library_id: Optional[str] = None) -> int:
        """Clear cached book data for a library (or all libraries)."""
        from .database import delete_all_books
        if library_id:
            count = await delete_books_for_library(library_id)
        else:
            await delete_all_books()
            count = -1
        return count

    def save_ruleset(self, ruleset: RuleSet) -> bool:
        return save_ruleset(ruleset)

    def get_ruleset(self) -> RuleSet:
        return load_ruleset()

    def reset_ruleset(self) -> RuleSet:
        """Reset the rule set to factory defaults and persist it."""
        from .rules.models import create_default_ruleset
        defaults = create_default_ruleset()
        save_ruleset(defaults)
        return defaults


def get_chapter_search_state() -> ChapterSearchState:
    return ChapterSearchState()
