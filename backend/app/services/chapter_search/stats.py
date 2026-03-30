"""Library statistics computation for Chapter Search."""

from __future__ import annotations

import re
from collections import Counter

from ...core.config import get_app_config
from .database import get_books_for_library


def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 0:
        return "0s"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _format_full_time_job(total_seconds: float) -> dict:
    """
    Format total library duration as a full-time job estimate.

    Uses 8-hour days, 5-day weeks, 4-week months, 12-month years.
    """
    total_hours = total_seconds / 3600
    days = total_hours / 8
    weeks = days / 5
    months = weeks / 4
    years = months / 12

    if total_hours < 8:
        return {"display": f"{total_hours:.1f} Hours", "value": total_hours, "unit": "Hours"}
    if days < 5:
        return {"display": f"{days:.1f} Days", "value": days, "unit": "Days"}
    if weeks < 4:
        return {"display": f"{weeks:.1f} Weeks", "value": weeks, "unit": "Weeks"}
    if months < 12:
        return {"display": f"{months:.1f} Months", "value": months, "unit": "Months"}
    return {"display": f"{years:.1f} Years", "value": years, "unit": "Years"}


_WORD_SPLIT_RE = re.compile(r"[^a-zA-Z]+")
_NUMBER_RE = re.compile(r"^\d+$")
_EXCLUDED_WORDS = {
    "chapter", "part", "credits", "opening", "end",
    "the", "a", "an", "of", "and", "in", "to", "for", "is", "it", "on", "at", "from", "with",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "evelen", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fourty",
    "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", 
    "s", "t", "m", "re", "ve", "ll", "d"
}


async def compute_library_stats(library_id: str) -> dict:
    """Compute aggregate statistics for a library's cached books and chapters."""
    books = await get_books_for_library(library_id)
    abs_url = get_app_config().abs.url

    total_books = len(books)
    if total_books == 0:
        return {
            "abs_url": abs_url,
            "total_books": 0,
            "total_chapters": 0,
            "avg_chapters": 0,
            "most_common_words": [],
            "most_chapters_book": None,
            "longest_chapter_title": None,
            "avg_chapter_length_seconds": 0,
            "avg_chapter_length": "0s",
            "avg_book_length_seconds": 0,
            "avg_book_length": "0s",
            "longest_chapter": None,
            "shortest_book": None,
            "longest_book": None,
            "total_library_seconds": 0,
            "total_library_duration": "0s",
            "full_time_job": {"display": "0 Hours"},
        }

    # --- Count-based stats ---

    all_chapters = []
    book_chapter_counts = []
    word_counter: Counter = Counter()

    for book in books:
        chapters = book.get("chapters", [])
        book_chapter_counts.append((book, len(chapters)))
        for ch in chapters:
            all_chapters.append((book, ch))
            title = ch.get("title", "")
            words = _WORD_SPLIT_RE.split(title.lower())
            for w in words:
                if w and w not in _EXCLUDED_WORDS and not _NUMBER_RE.match(w):
                    word_counter[w] += 1

    total_chapters = len(all_chapters)
    avg_chapters = round(total_chapters / total_books, 1)

    most_common_words = [
        {"word": word, "count": count}
        for word, count in word_counter.most_common(15)
    ]

    # Book with highest chapter count
    most_chapters_book_data, most_chapters_count = max(book_chapter_counts, key=lambda x: x[1])
    most_chapters_book = {
        "id": most_chapters_book_data["id"],
        "name": most_chapters_book_data["name"],
        "has_cover": most_chapters_book_data.get("has_cover", False),
        "chapter_count": most_chapters_count,
    }

    # Longest chapter title
    longest_title_book, longest_title_ch = max(
        all_chapters,
        key=lambda x: len(x[1].get("title", "")),
    )
    longest_chapter_title = {
        "title": longest_title_ch.get("title", ""),
        "book_id": longest_title_book["id"],
        "book_name": longest_title_book["name"],
        "has_cover": longest_title_book.get("has_cover", False),
    }

    # --- Duration-based stats ---

    chapter_durations = []
    book_durations = []

    for book in books:
        chapters = book.get("chapters", [])
        book_total = 0.0
        has_duration_data = False
        for ch in chapters:
            end = ch.get("end_time")
            start = ch.get("start_time", 0)
            if end is not None and end > start:
                duration = end - start
                chapter_durations.append((book, ch, duration))
                book_total += duration
                has_duration_data = True
        if has_duration_data:
            book_durations.append((book, book_total))

    if chapter_durations:
        avg_chapter_length_seconds = sum(d for _, _, d in chapter_durations) / len(chapter_durations)
    else:
        avg_chapter_length_seconds = 0

    if book_durations:
        avg_book_length_seconds = sum(d for _, d in book_durations) / len(book_durations)
    else:
        avg_book_length_seconds = 0

    # Longest chapter by duration
    if chapter_durations:
        longest_ch_book, longest_ch, longest_ch_dur = max(chapter_durations, key=lambda x: x[2])
        longest_chapter = {
            "title": longest_ch.get("title", ""),
            "duration_seconds": longest_ch_dur,
            "duration": _format_duration(longest_ch_dur),
            "book_id": longest_ch_book["id"],
            "book_name": longest_ch_book["name"],
            "has_cover": longest_ch_book.get("has_cover", False),
        }
    else:
        longest_chapter = None

    # Shortest and longest books by total duration
    if book_durations:
        shortest_book_data, shortest_book_dur = min(book_durations, key=lambda x: x[1])
        shortest_book = {
            "id": shortest_book_data["id"],
            "name": shortest_book_data["name"],
            "has_cover": shortest_book_data.get("has_cover", False),
            "duration_seconds": shortest_book_dur,
            "duration": _format_duration(shortest_book_dur),
        }
        longest_book_data, longest_book_dur = max(book_durations, key=lambda x: x[1])
        longest_book = {
            "id": longest_book_data["id"],
            "name": longest_book_data["name"],
            "has_cover": longest_book_data.get("has_cover", False),
            "duration_seconds": longest_book_dur,
            "duration": _format_duration(longest_book_dur),
        }
    else:
        shortest_book = None
        longest_book = None

    total_library_seconds = sum(d for _, d in book_durations)

    return {
        "abs_url": abs_url,
        "total_books": total_books,
        "total_chapters": total_chapters,
        "avg_chapters": avg_chapters,
        "most_common_words": most_common_words,
        "most_chapters_book": most_chapters_book,
        "longest_chapter_title": longest_chapter_title,
        "avg_chapter_length_seconds": avg_chapter_length_seconds,
        "avg_chapter_length": _format_duration(avg_chapter_length_seconds),
        "avg_book_length_seconds": avg_book_length_seconds,
        "avg_book_length": _format_duration(avg_book_length_seconds),
        "longest_chapter": longest_chapter,
        "shortest_book": shortest_book,
        "longest_book": longest_book,
        "total_library_seconds": total_library_seconds,
        "total_library_duration": _format_duration(total_library_seconds),
        "full_time_job": _format_full_time_job(total_library_seconds),
    }
