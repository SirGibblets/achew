import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "config" / "chapter_search.db"


@asynccontextmanager
async def _get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with _get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                library_id TEXT NOT NULL,
                name TEXT NOT NULL,
                author TEXT,
                series TEXT,
                has_cover INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                title TEXT NOT NULL,
                start_time REAL NOT NULL,
                PRIMARY KEY (book_id, position)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ignored_books (
                book_id TEXT PRIMARY KEY
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_books_library ON books(library_id)")
        await db.commit()
    logger.info(f"Chapter search database initialized at {DB_PATH}")


async def upsert_book(
    *,
    id: str,
    library_id: str,
    name: str,
    author: Optional[str],
    series: Optional[str],
    has_cover: bool,
    chapters: list[dict],
) -> None:
    """Insert or update a book and its chapters."""
    async with _get_db() as db:
        await db.execute(
            """
            INSERT INTO books (id, library_id, name, author, series, has_cover)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                library_id=excluded.library_id,
                name=excluded.name,
                author=COALESCE(excluded.author, author),
                series=COALESCE(excluded.series, series),
                has_cover=excluded.has_cover
            """,
            (id, library_id, name, author, series, int(has_cover)),
        )
        # Replace chapters entirely
        await db.execute("DELETE FROM chapters WHERE book_id = ?", (id,))
        await db.executemany(
            "INSERT INTO chapters (book_id, position, title, start_time) VALUES (?, ?, ?, ?)",
            [(id, i, ch["title"], ch["start_time"]) for i, ch in enumerate(chapters)],
        )
        await db.commit()


async def get_cached_book_ids(library_id: str) -> set[str]:
    """Return the set of book IDs already cached for a library."""
    async with _get_db() as db:
        async with db.execute(
            "SELECT id FROM books WHERE library_id = ?", (library_id,)
        ) as cursor:
            return {row["id"] async for row in cursor}


async def get_books_for_library(library_id: str) -> list[dict]:
    """Return all books with their chapters for a given library."""
    async with _get_db() as db:
        async with db.execute(
            """SELECT b.*, (ib.book_id IS NOT NULL) AS is_ignored
               FROM books b
               LEFT JOIN ignored_books ib ON b.id = ib.book_id
               WHERE b.library_id = ?
               ORDER BY b.name""",
            (library_id,),
        ) as cursor:
            books = [dict(row) for row in await cursor.fetchall()]

        for book in books:
            async with db.execute(
                "SELECT title, start_time FROM chapters WHERE book_id = ? ORDER BY position",
                (book["id"],),
            ) as cursor:
                book["chapters"] = [dict(row) for row in await cursor.fetchall()]
            book["is_ignored"] = bool(book["is_ignored"])
            book["has_cover"] = bool(book["has_cover"])

    return books


async def set_ignore(book_id: str, ignored: bool) -> None:
    """Set the ignore status of a book."""
    async with _get_db() as db:
        if ignored:
            await db.execute(
                "INSERT OR IGNORE INTO ignored_books (book_id) VALUES (?)", (book_id,)
            )
        else:
            await db.execute("DELETE FROM ignored_books WHERE book_id = ?", (book_id,))
        await db.commit()


async def get_book(book_id: str) -> Optional[dict]:
    """Return a single book with its chapters, or None if not cached."""
    async with _get_db() as db:
        async with db.execute(
            """SELECT b.*, (ib.book_id IS NOT NULL) AS is_ignored
               FROM books b
               LEFT JOIN ignored_books ib ON b.id = ib.book_id
               WHERE b.id = ?""",
            (book_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        book = dict(row)
        async with db.execute(
            "SELECT title, start_time FROM chapters WHERE book_id = ? ORDER BY position",
            (book_id,),
        ) as cursor:
            book["chapters"] = [dict(r) for r in await cursor.fetchall()]
        book["is_ignored"] = bool(book["is_ignored"])
        book["has_cover"] = bool(book["has_cover"])
    return book


async def upsert_chapters_for_book(book_id: str, chapters: list[dict]) -> None:
    """Replace chapter data for a cached book (used after ABS save)."""
    async with _get_db() as db:
        async with db.execute("SELECT id FROM books WHERE id = ?", (book_id,)) as cursor:
            if not await cursor.fetchone():
                return  # Book not in cache, nothing to update
        await db.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
        await db.executemany(
            "INSERT INTO chapters (book_id, position, title, start_time) VALUES (?, ?, ?, ?)",
            [(book_id, i, ch["title"], ch["start_time"]) for i, ch in enumerate(chapters)],
        )
        await db.commit()


async def delete_books_for_library(library_id: str) -> int:
    """Delete all cached books (and chapters via cascade) for a library. Returns count deleted."""
    async with _get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM books WHERE library_id = ?", (library_id,)
        ) as cursor:
            row = await cursor.fetchone()
            count = row["cnt"] if row else 0
        await db.execute("DELETE FROM books WHERE library_id = ?", (library_id,))
        await db.commit()
    return count


async def delete_all_books() -> None:
    """Delete all cached data."""
    async with _get_db() as db:
        await db.execute("DELETE FROM books")
        await db.commit()
