import logging
import traceback
from typing import List, Optional, Dict

from app.services.processing_pipeline import ExistingCueSource, PipelineProgress
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ...core.config import is_abs_configured
from ...models.abs import Book
from ...models.enums import RestartStep, Step
from ...app import get_app_state

logger = logging.getLogger(__name__)

router = APIRouter()


class CreatePipelineRequest(BaseModel):
    item_id: str


class CueSourceRequest(BaseModel):
    option: str


class RestartPipelineRequest(BaseModel):
    restart_step: RestartStep


class SmartDetectConfigRequest(BaseModel):
    segment_length: float
    min_clip_length: float
    asr_buffer: float
    min_silence_duration: float


class ASROptionsRequest(BaseModel):
    trim: bool
    use_bias_words: bool = False
    bias_words: str = ""


class ConfigureASRRequest(BaseModel):
    action: str  # "transcribe" or "skip"


class PipelineStateResponse(BaseModel):
    item_id: str
    step: str
    progress: PipelineProgress
    selection_stats: Dict[str, int]
    can_undo: bool
    can_redo: bool
    book: Optional[Book] = None
    cue_sources: List[ExistingCueSource] = []
    restart_options: List[str] = []


@router.post("/pipeline", response_model=dict)
async def create_pipeline(request: CreatePipelineRequest, background_tasks: BackgroundTasks):
    """Create a new processing pipeline"""
    # Check if API is configured
    if not is_abs_configured():
        raise HTTPException(
            status_code=400,
            detail="ABS configuration required. Please configure ABS API key first.",
        )

    try:
        app_state = get_app_state()
        pipeline = app_state.create_pipeline(request.item_id)

        # Start processing in background
        async def start_processing():
            try:
                result = await pipeline.fetch_item(request.item_id)
                logger.info(f"Fetched item: {result}")

                await app_state._broadcast_book_update()

                await app_state.broadcast_step_change(
                    Step.SELECT_CUE_SOURCE,
                    extras={"cue_sources": pipeline.existing_cue_sources},
                )

            except Exception as e:
                logger.error(f"Fetching item failed: {e}", exc_info=True)

        background_tasks.add_task(start_processing)

        return {
            "message": "Pipeline created and processing started",
        }

    except Exception as e:
        logger.error(f"Failed to create pipeline: {e}")
        traceback.print_exc()

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/state", response_model=PipelineStateResponse)
async def get_pipeline_state():
    """Get pipeline state details"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        pipeline = app_state.pipeline

        # Get stats from pipeline
        stats = pipeline.get_selection_stats()

        progress = PipelineProgress(
            step=pipeline.step,
            percent=0.0,  # Would need to get from pipeline
            message="",  # Would need to get from pipeline
            details={},
        )

        return PipelineStateResponse(
            item_id=pipeline.item_id,
            step=app_state.step.value,
            progress=progress,
            selection_stats=stats,
            can_undo=pipeline.can_undo(),
            can_redo=pipeline.can_redo(),
            book=pipeline.book if pipeline.book else None,
            cue_sources=pipeline.existing_cue_sources,
            restart_options=pipeline.get_restart_options(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get app state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pipeline")
async def delete_pipeline():
    """Delete the current pipeline and cleanup resources"""
    try:
        app_state = get_app_state()
        success = app_state.delete_pipeline()

        if not success:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        return {"message": "Pipeline deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/submit")
async def submit_chapters():
    """Submit chapters to Audiobookshelf"""
    try:
        app_state = get_app_state()
        pipeline = app_state.pipeline

        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        # Allow submission from chapter_editing or reviewing step
        if pipeline.step not in [Step.CHAPTER_EDITING, Step.REVIEWING]:
            raise HTTPException(
                status_code=400,
                detail="Pipeline must be in chapter_editing or reviewing step to submit",
            )

        success = await pipeline.submit_chapters(pipeline.chapters)

        if success:
            pipeline.step = Step.COMPLETED
            await app_state.broadcast_step_change(Step.COMPLETED)
            return {"message": "Chapters submitted successfully"}
        else:
            pipeline.step = Step.REVIEWING
            await app_state.broadcast_step_change(Step.REVIEWING)
            raise HTTPException(status_code=500, detail="Failed to submit chapters")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit chapters for pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/goto-review")
async def goto_review():
    """Transition from chapter editing to reviewing step"""
    try:
        app_state = get_app_state()
        pipeline = app_state.pipeline

        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if pipeline.step != Step.CHAPTER_EDITING:
            raise HTTPException(
                status_code=400,
                detail="Pipeline must be in chapter_editing step to go to review",
            )

        pipeline.step = Step.REVIEWING
        await app_state.broadcast_step_change(Step.REVIEWING)

        return {"message": "Transitioned to reviewing", "step": Step.REVIEWING.value}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to transition to reviewing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/cue-source")
async def select_cue_source(request: CueSourceRequest, background_tasks: BackgroundTasks):
    """Set cue source selection"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if app_state.step != Step.SELECT_CUE_SOURCE:
            raise HTTPException(
                status_code=400,
                detail="Pipeline must be in select_cue_source step to select option",
            )

        async def create_cues_from_source():
            try:
                await app_state.pipeline.create_cues_from_source(request.option)
            except Exception as e:
                logger.error(f"Failed to create cues from source: {e}")

        background_tasks.add_task(create_cues_from_source)

        return {
            "message": f"Selected cue source '{request.option}'",
            "option": request.option,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to select cue source for pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/cue-sets")
async def get_cue_sets():
    """Get available cue sets for user selection"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if app_state.step != Step.CUE_SET_SELECTION:
            raise HTTPException(
                status_code=400, detail=f"Pipeline not in cue set selection step. Current step: {app_state.step.value}"
            )

        # Get cue sets from pipeline data
        cue_sets = app_state.pipeline.cue_sets

        if not cue_sets:
            raise HTTPException(status_code=400, detail="No cue sets available")

        # Format options for frontend
        options = []
        for chapter_count, timestamps in cue_sets.items():
            avg_length = app_state.pipeline.book.duration / chapter_count if chapter_count > 0 else 0
            options.append(
                {
                    "chapter_count": chapter_count,
                    "timestamps": timestamps,
                    "average_length_minutes": round(avg_length / 60, 1),
                    "total_duration_hours": round(app_state.pipeline.book.duration / 3600, 2),
                }
            )

        # Sort by chapter count
        options.sort(key=lambda x: x["chapter_count"])

        return {
            "cue_sets": options,
            "book_duration": app_state.pipeline.book.duration,
            "existing_cue_sources": app_state.pipeline.existing_cue_sources,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cue sets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/select-cue-set")
async def select_cue_set(request: dict, background_tasks: BackgroundTasks):
    """Select a cue set"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if app_state.step != Step.CUE_SET_SELECTION:
            raise HTTPException(status_code=400, detail="Pipeline not in cue set selection step")

        chapter_count = request.get("chapter_count")
        if not chapter_count:
            raise HTTPException(status_code=400, detail="Chapter count is required")

        include_unaligned = request.get("include_unaligned", [])
        if not isinstance(include_unaligned, list):
            raise HTTPException(status_code=400, detail="include_unaligned must be a list")

        # Validate each option against available cue sources
        available_source_ids = [source.id for source in app_state.pipeline.existing_cue_sources]
        for option in include_unaligned:
            if option not in available_source_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid include_unaligned option: {option}. Available options: {available_source_ids}",
                )

        async def select_cue_set():
            try:
                # Use the new select_cue_set method that goes to CONFIGURE_ASR
                await app_state.pipeline.select_cue_set(chapter_count, include_unaligned)
            except Exception as e:
                logger.error(f"Failed to select cue set: {e}")

        background_tasks.add_task(select_cue_set)

        return {
            "message": "Cue set selected, extracting segments...",
            "include_unaligned": include_unaligned,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to select cue set: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/configure-asr")
async def configure_asr(request: ConfigureASRRequest, background_tasks: BackgroundTasks):
    """Configure ASR settings and proceed with transcription or skip"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if app_state.step != Step.CONFIGURE_ASR:
            raise HTTPException(
                status_code=400,
                detail="Pipeline must be in configure_asr step to configure ASR",
            )

        # Validate action
        if request.action not in ["transcribe", "skip"]:
            raise HTTPException(
                status_code=400,
                detail="Action must be 'transcribe' or 'skip'",
            )

        async def process_asr_action():
            try:
                if request.action == "transcribe":
                    await app_state.pipeline.proceed_with_transcription()
                elif request.action == "skip":
                    await app_state.pipeline.skip_transcription()
            except Exception as e:
                logger.error(f"Failed to process ASR action: {e}")

        background_tasks.add_task(process_asr_action)

        return {
            "message": f"ASR action '{request.action}' initiated",
            "action": request.action,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to configure ASR: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/segment-count")
async def get_segment_count():
    """Get the number of segments that will be transcribed"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if app_state.step != Step.CONFIGURE_ASR:
            raise HTTPException(
                status_code=400,
                detail="Pipeline must be in configure_asr step to get segment count",
            )

        segment_count = app_state.pipeline.get_segment_count()

        return {
            "segment_count": segment_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get segment count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/cue-sources", response_model=List[ExistingCueSource])
async def get_cue_sources():
    """Get detailed chapter information for available cue sources"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        return app_state.pipeline.existing_cue_sources

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cue sources for pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/restart")
async def restart_pipeline(request: RestartPipelineRequest):
    """Restart pipeline with selective cleanup"""
    try:
        app_state = get_app_state()
        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        await app_state.pipeline.restart_at_step(request.restart_step)

        return {
            "message": f"Pipeline restarted at step '{request.restart_step.value}'",
            "restart_step": request.restart_step.value,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restart pipeline: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/cancel")
async def cancel_step():
    """Cancel the current processing pipeline step and return to the appropriate previous step"""
    try:
        app_state = get_app_state()
        pipeline = app_state.pipeline

        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        step = pipeline.step

        if step in [Step.VALIDATING, Step.DOWNLOADING]:
            success = app_state.delete_pipeline()
            if not success:
                raise HTTPException(status_code=404, detail="Pipeline not found")
            return {"message": "Pipeline cancelled and deleted", "action": "deleted"}

        elif step in [Step.AUDIO_ANALYSIS, Step.VAD_PREP, Step.VAD_ANALYSIS]:
            await pipeline.restart_at_step(RestartStep.SELECT_CUE_SOURCE)
            return {
                "message": "Processing cancelled, returned to cue source selection",
                "action": "restarted",
                "restart_step": RestartStep.SELECT_CUE_SOURCE.value,
            }

        elif step == Step.AUDIO_EXTRACTION:
            if pipeline.cue_sets:
                await pipeline.restart_at_step(RestartStep.CUE_SET_SELECTION)
                return {
                    "message": "Audio extraction cancelled, returned to cue set selection",
                    "action": "restarted",
                    "restart_step": RestartStep.CUE_SET_SELECTION.value,
                }
            else:
                await pipeline.restart_at_step(RestartStep.SELECT_CUE_SOURCE)
                return {
                    "message": "Audio extraction cancelled, returned to cue source selection",
                    "action": "restarted",
                    "restart_step": RestartStep.SELECT_CUE_SOURCE.value,
                }

        elif step in [Step.TRIMMING, Step.ASR_PROCESSING]:
            await pipeline.restart_at_step(RestartStep.CONFIGURE_ASR)
            return {
                "message": "Transcription process cancelled, returned to ASR configuration",
                "action": "restarted",
                "restart_step": RestartStep.CONFIGURE_ASR.value,
            }

        else:
            await pipeline.restart_at_step(RestartStep.SELECT_CUE_SOURCE)
            return {
                "message": "Processing cancelled, returned to cue source selection",
                "action": "restarted",
                "restart_step": RestartStep.SELECT_CUE_SOURCE.value,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel current step: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pipeline/smart-detect-config")
async def update_smart_detect_config(request: SmartDetectConfigRequest):
    """Update smart detect configuration for the pipeline"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        # Update smart detect configuration in pipeline
        config_data = {
            "segment_length": request.segment_length,
            "min_clip_length": request.min_clip_length,
            "asr_buffer": request.asr_buffer,
            "min_silence_duration": request.min_silence_duration,
        }

        result = app_state.pipeline.update_smart_detect_config(config_data)

        if not result["success"]:
            raise HTTPException(status_code=400, detail={"errors": result["errors"]})

        return {
            "message": "Smart detect configuration updated successfully",
            "config": result["config"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update smart detect config for pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pipeline/asr-options")
async def update_asr_options(request: ASROptionsRequest):
    """Update ASR options for the pipeline"""
    try:
        from ...core.config import get_app_config, update_app_config

        # Update ASR options in config (persistent)
        app_config = get_app_config()
        app_config.asr_options.trim = request.trim
        app_config.asr_options.use_bias_words = request.use_bias_words
        app_config.asr_options.bias_words = request.bias_words

        success = update_app_config(app_config)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update ASR options")

        return {
            "message": "ASR options updated successfully",
            "options": app_config.asr_options.model_dump(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update ASR options for pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/asr-options")
async def get_asr_options():
    """Get ASR options for the current pipeline"""
    try:
        from ...core.config import get_app_config

        # Get ASR options from config (persistent)
        app_config = get_app_config()

        return {
            "options": app_config.asr_options.model_dump(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get ASR options for pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/smart-detect-config")
async def get_smart_detect_config():
    """Get smart detect configuration for the current pipeline"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        return {
            "config": app_state.pipeline.smart_detect_config.__dict__,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get smart detect config for pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))
