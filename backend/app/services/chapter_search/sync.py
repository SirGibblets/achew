"""ABS library sync service for Chapter Search.

Fetches book metadata and chapter data from ABS, storing it in the local SQLite cache.
Books already in the cache are skipped; only new books are fetched. Use "Clear Cache" to
force a full re-sync (e.g. after editing chapters directly in Audiobookshelf).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

import aiohttp

from ...core.config import get_app_config
from .database import get_cached_book_ids, upsert_book

logger = logging.getLogger(__name__)

# Max concurrent requests when fetching full book details
FETCH_CONCURRENCY = 6

# Number of items to request per page from the library endpoint
PAGE_SIZE = 100


def _abs_config():
    return get_app_config().abs


def _headers() -> dict:
    return {"Authorization": f"Bearer {_abs_config().api_key}"}


def _base_url() -> str:
    return _abs_config().url


async def sync_library(
    library_id: str,
    progress_cb: Callable[[str, int, int], None],
    cancel_event: asyncio.Event,
) -> tuple[int, int]:
    """
    Sync a library's chapter data to the local SQLite cache.

    Books already in the cache are skipped. Clear the cache to force a full re-sync.

    Args:
        library_id: ABS library ID
        progress_cb: called as progress_cb(task_name, current, total)
        cancel_event: set this to cancel the sync

    Returns:
        (synced_count, skipped_count) — books fetched vs. already cached
    """
    cached_ids = await get_cached_book_ids(library_id)

    async with aiohttp.ClientSession() as session:
        # Phase 1: collect all item IDs from ABS
        all_items = await _fetch_all_library_items(session, library_id, progress_cb, cancel_event)
        if cancel_event.is_set():
            return 0, 0

        # Phase 2: filter to items not already cached
        items_to_fetch = [item for item in all_items if item["id"] not in cached_ids]
        skipped = len(all_items) - len(items_to_fetch)
        total = len(items_to_fetch)

        logger.info(
            f"Library {library_id}: {len(all_items)} total, "
            f"{total} to fetch, {skipped} already cached"
        )

        if total == 0:
            progress_cb("sync", len(all_items), len(all_items))
            return 0, skipped

        # Phase 3: fetch full book details in parallel
        semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
        completed = 0

        async def fetch_and_store(item: dict) -> None:
            nonlocal completed
            if cancel_event.is_set():
                return
            async with semaphore:
                if cancel_event.is_set():
                    return
                await _fetch_and_cache_book(session, library_id, item)
                completed += 1
                progress_cb("sync", completed, total)

        tasks = [asyncio.create_task(fetch_and_store(item)) for item in items_to_fetch]
        await asyncio.gather(*tasks, return_exceptions=True)

    synced = completed
    return synced, skipped


async def _fetch_all_library_items(
    session: aiohttp.ClientSession,
    library_id: str,
    progress_cb: Callable,
    cancel_event: asyncio.Event,
) -> list[dict]:
    """Page through the library items endpoint and collect lightweight item metadata."""
    url = f"{_base_url()}/api/libraries/{library_id}/items"
    page = 0
    all_items: list[dict] = []

    while True:
        if cancel_event.is_set():
            break

        params = {
            "sort": "addedAt",
            "desc": 1,
            "limit": PAGE_SIZE,
            "page": page,
        }

        try:
            async with session.get(url, headers=_headers(), params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch library items page {page}: {resp.status}")
                    break
                data = await resp.json()
        except Exception as e:
            logger.error(f"Error fetching library items page {page}: {e}")
            break

        results = data.get("results", [])
        for item in results:
            # Only include audiobooks (must have audio files)
            if item.get("media", {}).get("numAudioFiles", 0) > 0:
                all_items.append({
                    "id": item["id"],
                    "name": item.get("media", {}).get("metadata", {}).get("title", ""),
                    "author": _extract_author(item.get("media", {}).get("metadata", {})),
                    "series": _extract_series(item),
                })

        total_items = data.get("total", 0)
        fetched_so_far = (page + 1) * PAGE_SIZE
        logger.debug(f"Library items page {page}: got {len(results)}, total={total_items}")

        if fetched_so_far >= total_items or not results:
            break
        page += 1

    return all_items


async def _fetch_and_cache_book(
    session: aiohttp.ClientSession,
    library_id: str,
    item: dict,
) -> None:
    """Fetch full book details and upsert into SQLite cache."""
    book_id = item["id"]
    url = f"{_base_url()}/api/items/{book_id}"

    try:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                logger.warning(f"Failed to fetch book {book_id}: {resp.status}")
                return
            data = await resp.json()
    except Exception as e:
        logger.warning(f"Error fetching book {book_id}: {e}")
        return

    media = data.get("media", {})
    metadata = media.get("metadata", {})
    chapters_raw = media.get("chapters", [])

    chapters = [
        {
            "title": ch.get("title", ""),
            "start_time": float(ch.get("start", 0)),
            "end_time": float(ch.get("end", 0)),
        }
        for ch in chapters_raw
    ]

    has_cover = bool(media.get("coverPath"))

    await upsert_book(
        id=book_id,
        library_id=library_id,
        name=metadata.get("title", item.get("name", "")),
        author=_extract_author(metadata) or item.get("author"),
        series=_extract_series_from_metadata(metadata) or item.get("series"),
        has_cover=has_cover,
        chapters=chapters,
    )


async def sync_specific_books(
    library_id: str,
    book_ids: list[str],
    progress_cb: Callable[[str, int, int], None],
    cancel_event: asyncio.Event,
) -> int:
    """Re-fetch and cache full details for a specific list of books. Returns count synced."""
    total = len(book_ids)
    completed = 0
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async with aiohttp.ClientSession() as session:
        async def fetch_and_store(book_id: str) -> None:
            nonlocal completed
            if cancel_event.is_set():
                return
            async with semaphore:
                if cancel_event.is_set():
                    return
                await _fetch_and_cache_book(session, library_id, {"id": book_id})
                completed += 1
                progress_cb("sync", completed, total)

        tasks = [asyncio.create_task(fetch_and_store(bid)) for bid in book_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

    return completed


def _extract_author(metadata: dict) -> Optional[str]:
    """Return author name, handling both the legacy `authorName` string and the new `authors` list."""
    author_name = metadata.get("authorName")
    if author_name:
        return author_name
    authors = metadata.get("authors")
    if authors and isinstance(authors, list) and authors:
        return authors[0].get("name")
    return None


def _extract_series(item: dict) -> Optional[str]:
    metadata = item.get("media", {}).get("metadata", {})
    return _extract_series_from_metadata(metadata)


def _extract_series_from_metadata(metadata: dict) -> Optional[str]:
    series_name = metadata.get("seriesName")
    if series_name:
        return series_name
    series_list = metadata.get("series")
    if series_list and isinstance(series_list, list) and series_list:
        return series_list[0].get("name")
    return None
