import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...core.config import is_abs_configured
from ...models.abs import Book
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
