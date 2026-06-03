import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import aiohttp

from ..core.config import get_app_config
from ..models.abs import AudnexusChapterList, Book
from .audible_providers import (
    all_regions,
    region_for_language,
    region_for_provider,
)

logger = logging.getLogger(__name__)

_library_cache: Dict[str, Dict] = {}
_library_provider_cache: Dict[str, Optional[str]] = {}


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

    async def search_library(self, library_id: str, query: str, limit: int = 12) -> List[Book]:
        """Search within a specific library, filter for books with audio files"""
        try:
            url = f"{self.config.url}/api/libraries/{library_id}/search"
            params = {"q": query, "limit": limit}
            async with self.session.get(url, headers=self._get_headers(), params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    books = []

                    # Process search results
                    if "book" in data and isinstance(data["book"], list):
                        for item in data["book"]:
                            if "libraryItem" in item:
                                library_item = item["libraryItem"]
                                # Check if book has audio files
                                if (
                                    library_item.get("media", {}).get("audioFiles")
                                    and len(library_item["media"]["audioFiles"]) > 0
                                ):
                                    try:
                                        book = Book(**library_item)
                                        books.append(book)
                                    except Exception as e:
                                        logger.warning(f"Failed to parse book data: {e}")
                                        continue

                    return books
                else:
                    logger.error(f"Failed to search library {library_id}: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Error searching library {library_id}: {e}")
            return []

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
                    books = []

                    if "results" in data and isinstance(data["results"], list):
                        for item in data["results"]:
                            if item.get("media", {}).get("numAudioFiles", 0) > 0:
                                try:
                                    book = Book(**item)
                                    if book.media and book.media.coverPath:
                                        book.media.coverPath = f"/api/audiobookshelf/covers/{book.id}"
                                    books.append(book)
                                except Exception as e:
                                    logger.warning(f"Failed to parse book data: {e}")
                                    continue

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
