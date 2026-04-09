import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...core.config import is_abs_configured
from ...models.abs import Book, BookSearchResult
from ...services.abs_service import ABSService

logger = logging.getLogger(__name__)

router = APIRouter()


class LibraryResponse(BaseModel):
    """Response model for library information"""

    id: str
    name: str
    mediaType: str


@router.get("/libraries", response_model=List[LibraryResponse])
async def get_libraries():
    """Get all available libraries filtered for book media type"""
    # Check if API is configured
    if not is_abs_configured():
        raise HTTPException(
            status_code=400,
            detail="API configuration required. Please configure ABS API key first.",
        )

    try:
        async with ABSService() as abs_service:
            # Check if ABS server is accessible
            if not await abs_service.health_check():
                raise HTTPException(
                    status_code=503,
                    detail="Unable to connect to Audiobookshelf server",
                )

            # Get libraries from ABS
            libraries = await abs_service.get_libraries()

            return libraries

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch libraries: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch libraries from Audiobookshelf server",
        )


@router.get("/libraries/{library_id}/search", response_model=List[Book])
async def search_library(
    library_id: str,
    q: str = Query(..., description="Search query"),
):
    """Search for books within a specific library"""
    # Check if API is configured
    if not is_abs_configured():
        raise HTTPException(
            status_code=400,
            detail="API configuration required. Please configure ABS API key first.",
        )

    # Validate query parameter
    if not q or len(q.strip()) < 2:
        raise HTTPException(
            status_code=400,
            detail="Search query must be at least 2 characters long",
        )

    try:
        async with ABSService() as abs_service:
            # Check if ABS server is accessible
            if not await abs_service.health_check():
                raise HTTPException(
                    status_code=503,
                    detail="Unable to connect to Audiobookshelf server",
                )

            # Search within the specified library
            search_results = await abs_service.search_library(library_id, q.strip())

            # Add proper cover URLs to the results
            for book in search_results:
                if book.media and book.media.coverPath:
                    book.media.coverPath = f"/api/audiobookshelf/covers/{book.id}"

            return search_results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search library {library_id} with query '{q}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to search library",
        )


@router.get("/libraries/{library_id}/items", response_model=List[Book])
async def get_library_items(
    library_id: str,
    refresh: bool = Query(False, description="Clear cache and fetch fresh data"),
):
    """Get all items from a specific library"""
    if not is_abs_configured():
        raise HTTPException(
            status_code=400,
            detail="API configuration required. Please configure ABS API key first.",
        )

    try:
        async with ABSService() as abs_service:
            if not await abs_service.health_check():
                raise HTTPException(
                    status_code=503,
                    detail="Unable to connect to Audiobookshelf server",
                )

            if refresh:
                ABSService.clear_library_cache(library_id)

            return await abs_service.get_library_items(library_id, use_cache=not refresh)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch library items from {library_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch library items",
        )


@router.post("/cache/clear")
async def clear_all_cache():
    """Clear all library caches"""
    try:
        ABSService.clear_library_cache()
        return {"message": "All library caches cleared"}
    except Exception as e:
        logger.error(f"Failed to clear all caches: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to clear caches",
        )


@router.get("/covers/{item_id}")
async def proxy_cover(item_id: str):
    """Proxy audiobook cover images"""
    if not is_abs_configured():
        raise HTTPException(status_code=503, detail="ABS not configured")

    try:
        async with ABSService() as abs_service:
            cover_url = f"{abs_service.config.url}/api/items/{item_id}/cover"
            headers = abs_service._get_headers()

            async with abs_service.session.get(cover_url, headers=headers) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get("content-type", "image/jpeg")
                    content = await resp.read()

                    return StreamingResponse(
                        iter([content]),
                        media_type=content_type,
                        headers={"Cache-Control": "public, max-age=3600"},
                    )
                else:
                    raise HTTPException(status_code=resp.status, detail="Cover not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying cover for {item_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cover")


class BookSearchResultWithChapters(BookSearchResult):
    chapter_count: Optional[int] = None
    chapters: Optional[list] = None


@router.get("/search/books", response_model=List[BookSearchResultWithChapters])
async def search_books(
    provider: str = Query(..., description="Audible provider identifier"),
    title: str = Query("", description="Book title or ASIN to search for"),
    author: str = Query("", description="Author name"),
    id: Optional[str] = Query(None, description="Book ID"),
):
    """Search for books via ABS and add Audnexus chapter data."""
    if not is_abs_configured():
        raise HTTPException(status_code=503, detail="ABS not configured")

    # If book ID is not specified, attempt to obtain it from the active pipeline
    if not id:
        from ...app import get_app_state
        app_state = get_app_state()
        if app_state.pipeline and app_state.pipeline.book and app_state.pipeline.book.id:
            id = app_state.pipeline.book.id
        else:
            id = ""

    try:
        async with ABSService() as abs_service:
            results = await abs_service.search_books(
                provider=provider,
                title=title,
                author=author,
                book_id=id,
            )

        if not results:
            return []
        
        # Sort by confidence and cap at 10
        results.sort(key=lambda r: r.matchConfidence or 0.0, reverse=True)
        results = results[:10]

        # Determine region from provider (e.g. "audible.uk" -> "UK", "audible" -> "US")
        region = provider.split(".")[-1].upper() if "." in provider else "US"

        # Fetch Audnexus chapter data for each result concurrently
        async def _enrich(result: BookSearchResult) -> Optional[BookSearchResultWithChapters]:
            if not result.asin:
                return None
            try:
                async with ABSService() as svc:
                    chapter_data = await svc.get_audnexus_chapters(result.asin, region=region)
                if not chapter_data or not chapter_data.chapters:
                    return None
                    
                enriched = BookSearchResultWithChapters(**result.model_dump())
                enriched.chapter_count = len(chapter_data.chapters)
                enriched.chapters = [
                    {"timestamp": ch.startOffsetMs / 1000, "title": ch.title}
                    for ch in chapter_data.chapters
                ]
                return enriched
            except Exception as e:
                logger.warning(f"Could not fetch Audnexus chapters for {result.asin}: {e}")
                return None

        enriched_results = await asyncio.gather(*[_enrich(r) for r in results])
        # Exclude results that couldn't be enriched with chapter data
        return [r for r in enriched_results if r is not None]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Book search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Book search failed")
