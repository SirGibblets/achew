import logging
import importlib.metadata

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.config import get_configuration_status, is_abs_configured
from ...models.enums import Step
from ...services.abs_service import ABSService
from ...app import AppState, get_app_state

logger = logging.getLogger(__name__)

router = APIRouter()


def get_app_version():
    """Get the application version from package metadata"""
    try:
        return importlib.metadata.version("achew")
    except importlib.metadata.PackageNotFoundError:
        # Fallback to a default version if package is not installed
        return "vDEV"


class ValidateItemRequest(BaseModel):
    item_id: str


class ValidateItemResponse(BaseModel):
    valid: bool
    book_title: str = None
    book_duration: float = None
    cover_url: str = None
    file_count: int = None
    error_message: str = None


@router.post("/validate-item", response_model=ValidateItemResponse)
async def validate_item(request: ValidateItemRequest):
    """Validate an item ID and return basic book information"""
    # Check if API is configured
    if not is_abs_configured():
        return ValidateItemResponse(
            valid=False,
            error_message="ABS configuration required. Please configure ABS API key first.",
        )

    try:
        async with ABSService() as abs_service:
            # Check if ABS server is accessible
            if not await abs_service.health_check():
                return ValidateItemResponse(
                    valid=False,
                    error_message="Unable to connect to Audiobookshelf server",
                )

            # Try to get book details
            book = await abs_service.get_book_details(request.item_id)
            if not book:
                return ValidateItemResponse(
                    valid=False,
                    error_message="Item not found on Audiobookshelf server",
                )

            # Generate cover URL using ABS API endpoint
            cover_url = None
            if book.media and book.media.coverPath:
                cover_url = f"{abs_service.config.url}/api/items/{request.item_id}/cover"

            return ValidateItemResponse(
                valid=True,
                book_title=book.media.metadata.title if (book.media and book.media.metadata) else "Unknown Title",
                book_duration=book.duration,
                cover_url=cover_url,
                file_count=len(book.media.audioFiles),
            )

    except Exception as e:
        logger.error(f"Failed to validate item {request.item_id}: {e}")
        return ValidateItemResponse(
            valid=False,
            error_message="Failed to validate item. Please check the ID and try again.",
        )


@router.get("/status")
async def get_app_status():
    """Get app status and configuration info"""
    try:
        app_state = get_app_state()
        config_status = get_configuration_status()

        result = {
            "has_pipeline": app_state.pipeline is not None,
            "step": app_state.step.value,
            "abs_configured": config_status["abs_configured"],
            "config_status": config_status,
            "version": get_app_version(),
        }

        if app_state.pipeline:
            pipeline = app_state.pipeline
            stats = pipeline.get_selection_stats()
            result.update(
                {
                    "item_id": pipeline.item_id,
                    "total_chapters": len(pipeline.chapters),
                    "selected_chapters": stats["selected"],
                }
            )

        return result

    except Exception as e:
        logger.error(f"Failed to get app status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/goto-abs-setup")
async def goto_abs_setup():
    """Transition to ABS setup step"""
    try:
        app_state: AppState = get_app_state()

        previous_step = None

        # Store the previous step if we have an active pipeline
        if app_state.pipeline and app_state.step != Step.ABS_SETUP:
            previous_step = app_state.step

        # Set step to ABS_SETUP
        app_state.step = Step.ABS_SETUP

        # Broadcast step change
        await app_state.broadcast_step_change(Step.ABS_SETUP)

        return {
            "message": "Transitioned to ABS setup",
            "step": Step.ABS_SETUP.value,
            "previous_step": previous_step.value if previous_step else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to transition to ABS setup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/goto-llm-setup")
async def goto_llm_setup():
    """Transition to LLM setup step"""
    try:
        app_state = get_app_state()

        # Check if ABS is configured first
        if not is_abs_configured():
            raise HTTPException(status_code=400, detail="ABS must be configured before accessing LLM setup")

        previous_step = None

        # Store the previous step if we have an active pipeline
        if app_state.pipeline and app_state.step != Step.LLM_SETUP:
            previous_step = app_state.step

        # Set step to LLM_SETUP
        app_state.step = Step.LLM_SETUP

        # Broadcast step change
        await app_state.broadcast_step_change(Step.LLM_SETUP)

        return {
            "message": "Transitioned to LLM setup",
            "step": Step.LLM_SETUP.value,
            "previous_step": previous_step.value if previous_step else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to transition to LLM setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/complete-llm-setup")
async def complete_llm_setup():
    """Complete LLM setup and return to idle"""
    try:
        app_state = get_app_state()

        if app_state.step != Step.LLM_SETUP:
            raise HTTPException(status_code=400, detail="Must be in LLM setup step to complete")

        # Transition to idle
        app_state.step = None
        await app_state.broadcast_step_change(Step.IDLE)

        return {"message": "LLM setup completed", "step": Step.IDLE.value}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to complete LLM setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/complete-abs-setup")
async def complete_abs_setup():
    """Complete ABS setup and transition to LLM setup"""
    try:
        # Check if ABS is now properly configured
        if not is_abs_configured():
            raise HTTPException(status_code=400, detail="ABS configuration is not valid")

        app_state = get_app_state()

        # Set step to LLM_SETUP
        app_state.step = Step.LLM_SETUP

        # Broadcast step change
        await app_state.broadcast_step_change(Step.LLM_SETUP)

        return {"message": "ABS setup completed, proceeding to LLM setup", "step": Step.LLM_SETUP.value}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to complete ABS setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))
