"""Chapter search execution service.

Evaluates rules against all cached books in a library and returns matches.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from .database import get_books_for_library
from .rules.evaluator import evaluate_ruleset
from .rules.models import RuleSet

logger = logging.getLogger(__name__)


async def run_search(
    library_id: str,
    ruleset: RuleSet,
    progress_cb: Callable[[str, int, int], None],
    cancel_event: asyncio.Event,
) -> list[dict]:
    """
    Evaluate the ruleset against every cached book in the library.

    Returns a list of matched books sorted alphabetically by name, each with:
      - id, name, author, series, has_cover, is_ignored
      - chapters: list of {title, start_time}
      - matched_rule_ids: list of rule IDs that caused the match
    """
    books = await get_books_for_library(library_id)
    total = len(books)
    results: list[dict] = []

    for i, book in enumerate(books):
        if cancel_event.is_set():
            break

        chapter_titles = [ch["title"] for ch in book.get("chapters", [])]
        matched, matched_ids = evaluate_ruleset(ruleset, book["name"], chapter_titles)

        if matched:
            results.append({
                "id": book["id"],
                "name": book["name"],
                "author": book.get("author"),
                "series": book.get("series"),
                "has_cover": book.get("has_cover", False),
                "is_ignored": book.get("is_ignored", False),
                "chapters": book.get("chapters", []),
                "matched_rule_ids": matched_ids,
            })

        progress_cb("search", i + 1, total)

        # Yield control periodically so the event loop can process other tasks
        if (i + 1) % 50 == 0:
            await asyncio.sleep(0)

    # Sort alphabetically by name
    results.sort(key=lambda b: b["name"].lower())
    return results
