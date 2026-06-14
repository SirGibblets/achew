import logging
import traceback
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.models.references import ChapterReference, TitleReference
from app.services.processing_pipeline import PipelineProgress

from ...app import get_app_state
from ...core.config import is_abs_configured
from ...models.abs import AudioInfo, Book
from ...models.enums import RestartStep, Step

logger = logging.getLogger(__name__)

router = APIRouter()


class CreatePipelineRequest(BaseModel):
    item_id: str


class StartWorkflowRequest(BaseModel):
    workflow: str
    ref_id: Optional[str] = None
    dramatized: Optional[bool] = False
    thorough: Optional[bool] = False


class RestartPipelineRequest(BaseModel):
    restart_step: RestartStep


class ASROptionsRequest(BaseModel):
    trim: bool
    use_bias_words: bool = False
    bias_words: str = ""
    segment_length: float = 8.0


class PreassignedTitle(BaseModel):
    cue_index: int
    title: str


class ConfigureASRRequest(BaseModel):
    action: str  # "transcribe" or "skip"
    preassigned_titles: List[PreassignedTitle] = []


class PipelineStateResponse(BaseModel):
    item_id: str
    step: str
    progress: PipelineProgress
    selection_stats: Dict[str, int]
    can_undo: bool
    can_redo: bool
    book: Optional[Book] = None
    chapter_refs: List[ChapterReference] = []
    title_refs: List[TitleReference] = []
    restart_options: List[str] = []
    audio_unsupported_codec: bool = False
    audio_info: Optional[AudioInfo] = None


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
                    Step.SELECT_WORKFLOW,
                    extras={
                        "chapter_refs": pipeline.chapter_refs,
                        "title_refs": pipeline.title_refs,
                        "audio_unsupported_codec": pipeline.audio_unsupported_codec,
                        "audio_info": pipeline.audio_info,
                    },
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
            chapter_refs=pipeline.chapter_refs,
            title_refs=pipeline.title_refs,
            restart_options=pipeline.get_restart_options(),
            audio_unsupported_codec=pipeline.audio_unsupported_codec,
            audio_info=pipeline.audio_info,
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
        success = await app_state.delete_pipeline()

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


@router.post("/pipeline/start-workflow")
async def start_workflow(request: StartWorkflowRequest, background_tasks: BackgroundTasks):
    """Set workflow"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if app_state.step != Step.SELECT_WORKFLOW:
            raise HTTPException(
                status_code=400,
                detail="Pipeline must be in select_workflow step to select option",
            )

        pipeline = app_state.pipeline

        async def run_workflow():
            try:
                await pipeline.start_workflow(request.workflow, request.ref_id, request.dramatized, request.thorough)
            except Exception as e:
                logger.error(f"Failed to start workflow: {e}")

        background_tasks.add_task(run_workflow)

        return {
            "message": f"Selected workflow '{request.workflow}'",
            "workflow": request.workflow,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to select workflow for pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/detected-cues")
async def get_detected_cues():
    """Get all detected cues for initial chapter selection"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if app_state.step != Step.INITIAL_CHAPTER_SELECTION:
            raise HTTPException(
                status_code=400,
                detail=f"Pipeline not in initial chapter selection step. Current step: {app_state.step.value}",
            )

        if not app_state.pipeline.detected_cues:
            raise HTTPException(status_code=400, detail="No detected cues available")

        # Sort by timestamp
        detected_cues = app_state.pipeline.detected_cues.copy()
        detected_cues.sort(key=lambda x: x.timestamp)

        return {
            "detected_cues": detected_cues,
            "book_duration": app_state.pipeline.book_duration,
            "chapter_refs": app_state.pipeline.chapter_refs,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get detected cues: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/select-initial-chapters")
async def select_initial_chapters(request: dict, background_tasks: BackgroundTasks):
    """Select initial chapters by providing a list of cue timestamps"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if app_state.step != Step.INITIAL_CHAPTER_SELECTION:
            raise HTTPException(status_code=400, detail="Pipeline not in initial chapter selection step")

        timestamps = request.get("timestamps")
        if timestamps is None or not isinstance(timestamps, list):
            raise HTTPException(status_code=400, detail="timestamps must be a list of floats")
        if len(timestamps) == 0:
            raise HTTPException(status_code=400, detail="At least one timestamp is required")

        include_unaligned = request.get("include_unaligned", [])
        if not isinstance(include_unaligned, list):
            raise HTTPException(status_code=400, detail="include_unaligned must be a list")

        # Validate each option against available chapter references
        available_ref_ids = [ref.id for ref in app_state.pipeline.chapter_refs]
        for option in include_unaligned:
            if option not in available_ref_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid include_unaligned option: {option}. Available options: {available_ref_ids}",
                )

        pipeline = app_state.pipeline

        async def do_select_initial_chapters():
            try:
                await pipeline.select_initial_chapters(timestamps, include_unaligned)
            except Exception as e:
                logger.error(f"Failed to select initial chapters: {e}")

        background_tasks.add_task(do_select_initial_chapters)

        return {
            "message": "Initial chapters selected, extracting segments…",
            "include_unaligned": include_unaligned,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to select initial chapters: {e}")
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

        pipeline = app_state.pipeline

        # Validate preassigned titles and build the cue_index -> title map
        cue_count = len(pipeline.cues)
        preassigned: Dict[int, str] = {}
        for item in request.preassigned_titles:
            if item.cue_index < 0 or item.cue_index >= cue_count:
                raise HTTPException(
                    status_code=400,
                    detail=f"preassigned_titles cue_index {item.cue_index} out of range [0, {cue_count})",
                )
            if item.cue_index in preassigned:
                raise HTTPException(
                    status_code=400,
                    detail=f"preassigned_titles contains duplicate cue_index {item.cue_index}",
                )
            preassigned[item.cue_index] = item.title

        async def process_asr_action():
            try:
                if request.action == "transcribe":
                    await pipeline.proceed_with_transcription(preassigned_titles=preassigned)
                elif request.action == "skip":
                    await pipeline.skip_transcription(preassigned_titles=preassigned)
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


@router.get("/pipeline/selected-cues")
async def get_selected_cues():
    """Get the cues that are queued for transcription"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if app_state.step != Step.CONFIGURE_ASR:
            raise HTTPException(
                status_code=400,
                detail="Pipeline must be in configure_asr step to get selected cues",
            )

        return {
            "cues": list(app_state.pipeline.cues),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get selected cues: {e}")
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
            success = await app_state.delete_pipeline()
            if not success:
                raise HTTPException(status_code=404, detail="Pipeline not found")
            return {"message": "Pipeline cancelled and deleted", "action": "deleted"}

        elif step in [Step.AUDIO_ANALYSIS, Step.VAD_PREP, Step.VAD_ANALYSIS]:
            await pipeline.restart_at_step(RestartStep.SELECT_WORKFLOW)
            return {
                "message": "Processing cancelled, returned to workflow selection",
                "action": "restarted",
                "restart_step": RestartStep.SELECT_WORKFLOW.value,
            }

        elif step == Step.AUDIO_EXTRACTION:
            restart_step = RestartStep.SELECT_WORKFLOW if pipeline.is_realignment else RestartStep.CONFIGURE_ASR
            await pipeline.restart_at_step(restart_step)
            return {
                "message": f"Audio extraction cancelled, returned to {restart_step.value}",
                "action": "restarted",
                "restart_step": restart_step.value,
            }

        elif step in [Step.TRIMMING, Step.ASR_PROCESSING]:
            await pipeline.restart_at_step(RestartStep.CONFIGURE_ASR)
            return {
                "message": "Transcription process cancelled, returned to ASR configuration",
                "action": "restarted",
                "restart_step": RestartStep.CONFIGURE_ASR.value,
            }

        elif step in [Step.AI_CLEANUP, Step.PARTIAL_SCAN_PREP, Step.PARTIAL_AUDIO_ANALYSIS, Step.PARTIAL_VAD_ANALYSIS]:
            await pipeline.restart_at_step(RestartStep.CHAPTER_EDITING)
            return {
                "message": "Processing cancelled, returned to chapter editing",
                "action": "restarted",
                "restart_step": RestartStep.CHAPTER_EDITING.value,
            }

        else:
            await pipeline.restart_at_step(RestartStep.SELECT_WORKFLOW)
            return {
                "message": "Processing cancelled, returned to workflow selection",
                "action": "restarted",
                "restart_step": RestartStep.SELECT_WORKFLOW.value,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel current step: {e}")
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
        app_config.asr_options.segment_length = request.segment_length

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
