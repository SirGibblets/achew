"""REST API routes for Chapter Search"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ....services.chapter_search.rules.models import RuleSet
from ....services.chapter_search.state import get_chapter_search_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chapter-search", tags=["chapter-search"])


class SaveRulesetRequest(BaseModel):
    ruleset: dict


class ToggleIgnoreRequest(BaseModel):
    book_id: str


class ClearCacheRequest(BaseModel):
    library_id: Optional[str] = None


@router.get("/ruleset")
async def get_ruleset():
    """Return the current root rule set."""
    state = get_chapter_search_state()
    ruleset = state.get_ruleset()
    return {"ruleset": ruleset.model_dump()}


@router.put("/ruleset")
async def save_ruleset(request: SaveRulesetRequest):
    """Save an updated rule set to persistent storage."""
    try:
        ruleset = RuleSet.model_validate(request.ruleset)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid ruleset: {e}")

    state = get_chapter_search_state()
    ok = state.save_ruleset(ruleset)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save ruleset")

    # Broadcast updated landing state so all clients see the new rules
    if state.page == "landing":
        await state.broadcast_state()

    return {"ok": True}


@router.post("/ignore/{book_id}")
async def toggle_ignore(book_id: str):
    """Toggle the ignore status of a book in the search results."""
    state = get_chapter_search_state()
    await state.toggle_ignore(book_id)
    return {"ok": True}


@router.post("/ruleset/reset")
async def reset_ruleset():
    """Reset the rule set to factory defaults."""
    state = get_chapter_search_state()
    state.reset_ruleset()
    if state.page == "landing":
        await state.broadcast_state()
    return {"ok": True}


@router.post("/clear-cache")
async def clear_cache(request: ClearCacheRequest):
    """Clear cached book/chapter data for a library or all libraries."""
    state = get_chapter_search_state()
    count = await state.clear_cache(request.library_id)
    return {"ok": True, "deleted_count": count}
