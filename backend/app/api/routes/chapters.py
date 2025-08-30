import logging
from typing import List, Dict, Any
import csv
import json
import io
from datetime import datetime

from app.models.chapter_operation import (
    AddChapterOperation,
    ChapterOperation,
    DeleteChapterOperation,
    EditTitleOperation,
    RestoreChapterOperation,
)
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ...app import get_app_state

logger = logging.getLogger(__name__)

router = APIRouter()


class ChapterResponse(BaseModel):
    id: str
    timestamp: float
    asr_title: str
    current_title: str
    selected: bool


class ChaptersListResponse(BaseModel):
    chapters: List[ChapterResponse]
    selection_stats: Dict[str, int]
    total_count: int


class UpdateTitleRequest(BaseModel):
    title: str


class ToggleSelectionRequest(BaseModel):
    selected: bool


class UndoRedoRequest(BaseModel):
    pass


class BatchOperationRequest(BaseModel):
    pass


class AIOptions(BaseModel):
    inferOpeningCredits: bool = True
    inferEndCredits: bool = True
    deselectNonChapters: bool = True
    keepDeselectedTitles: bool = False
    usePreferredTitles: bool = False
    preferredTitlesSource: str = ""
    additionalInstructions: str = ""
    provider_id: str = ""
    model_id: str = ""


class ProcessSelectedRequest(BaseModel):
    ai_options: AIOptions = AIOptions()


class BatchOperationResponse(BaseModel):
    message: str
    affected_chapters: int


class HistoryAction(BaseModel):
    action_type: str
    timestamp: str
    data: Dict[str, Any]


class HistoryResponse(BaseModel):
    history: List[HistoryAction]
    current_index: int
    can_undo: bool
    can_redo: bool


class DetectedCue(BaseModel):
    timestamp: float
    gap: float


class ExistingCue(BaseModel):
    timestamp: float
    title: str


class DeletedChapter(BaseModel):
    timestamp: float
    title: str


class AddOptionsResponse(BaseModel):
    min_timestamp: float
    max_timestamp: float
    detected_cues: List[DetectedCue]
    existing_cues: Dict[str, List[ExistingCue]]
    deleted: List[DeletedChapter]


class AddChapterRequest(BaseModel):
    timestamp: float
    title: str = ""


@router.get("/chapters", response_model=ChaptersListResponse)
async def get_chapters():
    """Get all chapters for the current session"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        chapters_data = []
        for chapter in app_state.pipeline.chapters:
            if not chapter.deleted:
                chapters_data.append(
                    ChapterResponse(
                        id=chapter.id,
                        timestamp=chapter.timestamp,
                        asr_title=chapter.asr_title,
                        current_title=chapter.current_title,
                        selected=chapter.selected,
                    )
                )

        stats = app_state.pipeline.get_selection_stats()

        return ChaptersListResponse(
            chapters=chapters_data,
            selection_stats=stats,
            total_count=len(app_state.pipeline.chapters),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chapters for session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/chapters/{chapter_id}/title")
async def update_chapter_title(chapter_id: str, request: UpdateTitleRequest):
    """Update a chapter's title"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        operation = EditTitleOperation(chapter_id=chapter_id, new_title=request.title)
        operation.apply(app_state.pipeline)
        app_state.pipeline.add_to_history(operation)

        # Broadcast updates
        await app_state.broadcast_chapter_update()
        await app_state.broadcast_history_update()

        return {"message": "Chapter title updated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update chapter title: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/chapters/{chapter_id}/select")
async def toggle_chapter_selection(chapter_id: str, request: ToggleSelectionRequest):
    """Toggle chapter selection status"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        # Find the chapter
        chapter = None
        for ch in app_state.pipeline.chapters:
            if ch.id == chapter_id:
                chapter = ch
                break

        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")

        # Update selection
        chapter.selected = request.selected

        # Broadcast updates
        await app_state.broadcast_chapter_update()

        return {"message": "Chapter selection updated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle chapter selection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(chapter_id: str):
    """Delete a chapter"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        operation = DeleteChapterOperation(chapter_id=chapter_id)
        operation.apply(app_state.pipeline)
        app_state.pipeline.add_to_history(operation)

        # Broadcast updates
        await app_state.broadcast_chapter_update()
        await app_state.broadcast_history_update()

        return {"message": "Chapter deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete chapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chapters/select-all", response_model=BatchOperationResponse)
async def select_all(request: BatchOperationRequest):
    """Select all chapters"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        affected_count = 0

        for chapter in app_state.pipeline.chapters:
            if not chapter.selected:
                chapter.selected = True
                affected_count += 1

        if affected_count > 0:
            # Broadcast updates
            await app_state.broadcast_chapter_update()

        return BatchOperationResponse(
            message=f"Selected {affected_count} chapters",
            affected_chapters=affected_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to select all chapters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chapters/deselect-all", response_model=BatchOperationResponse)
async def deselect_all(request: BatchOperationRequest):
    """Deselect all chapters"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        affected_count = 0

        for chapter in app_state.pipeline.chapters:
            if chapter.selected:
                chapter.selected = False
                affected_count += 1

        if affected_count > 0:
            # Broadcast updates
            await app_state.broadcast_chapter_update()

        return BatchOperationResponse(
            message=f"Deselected {affected_count} chapters",
            affected_chapters=affected_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deselect all chapters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chapters/ai-cleanup", response_model=BatchOperationResponse)
async def ai_cleanup(request: ProcessSelectedRequest):
    """Process selected chapters with AI"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        # Get selected chapters
        selected_chapters = [ch for ch in app_state.pipeline.chapters if ch.selected]

        if not selected_chapters:
            return BatchOperationResponse(
                message="No chapters selected for processing",
                affected_chapters=0,
            )

        success = await app_state.pipeline.process_selected_with_ai(request.ai_options)

        if not success:
            raise HTTPException(status_code=500, detail="AI cleanup failed")

        # Broadcast updates after AI cleanup
        await app_state.broadcast_chapter_update()
        await app_state.broadcast_history_update()

        return BatchOperationResponse(
            message=f"Processed {len(selected_chapters)} chapters with AI",
            affected_chapters=len(selected_chapters),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process selected chapters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chapters/ai-options", response_model=AIOptions)
async def get_ai_options():
    """Get the current AI cleanup options for the session"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        # Load saved preferences from config
        from ...core.config import get_app_config

        config = get_app_config()

        # Convert pipeline AIOptions to the API AIOptions format
        pipeline_options = app_state.pipeline.ai_options
        return AIOptions(
            inferOpeningCredits=pipeline_options.inferOpeningCredits,
            inferEndCredits=pipeline_options.inferEndCredits,
            deselectNonChapters=pipeline_options.deselectNonChapters,
            keepDeselectedTitles=pipeline_options.keepDeselectedTitles,
            usePreferredTitles=pipeline_options.usePreferredTitles,
            preferredTitlesSource=pipeline_options.preferredTitlesSource,
            additionalInstructions=pipeline_options.additionalInstructions,
            provider_id=config.llm.last_used_provider,
            model_id=config.llm.last_used_model,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get AI options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/chapters/ai-options", response_model=AIOptions)
async def update_ai_options(ai_options: AIOptions):
    """Update the AI cleanup options for the session"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        # Save provider/model preferences to config
        from ...core.config import get_app_config, save_llm_config

        config = get_app_config()
        config.llm.last_used_provider = ai_options.provider_id
        config.llm.last_used_model = ai_options.model_id
        save_llm_config(config.llm)

        # Convert the API AIOptions to the pipeline's AIOptions format
        from ...services.processing_pipeline import AIOptions as PipelineAIOptions

        pipeline_ai_options = PipelineAIOptions(
            inferOpeningCredits=ai_options.inferOpeningCredits,
            inferEndCredits=ai_options.inferEndCredits,
            deselectNonChapters=ai_options.deselectNonChapters,
            keepDeselectedTitles=ai_options.keepDeselectedTitles,
            usePreferredTitles=ai_options.usePreferredTitles,
            preferredTitlesSource=ai_options.preferredTitlesSource,
            additionalInstructions=ai_options.additionalInstructions,
            provider_id=ai_options.provider_id,
            model_id=ai_options.model_id,
        )
        app_state.pipeline.ai_options = pipeline_ai_options

        # Return the original format
        return ai_options

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update AI options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chapters/undo")
async def undo_action(request: UndoRedoRequest):
    """Undo the last action"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if not app_state.pipeline.can_undo():
            raise HTTPException(status_code=400, detail="Nothing to undo")

        # Perform undo
        app_state.pipeline.undo()

        # Broadcast updates
        await app_state.broadcast_chapter_update()
        await app_state.broadcast_history_update()

        return {"message": "Action undone"}

    except HTTPException as e:
        logger.error(f"Failed to undo action: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Failed to undo action: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chapters/redo")
async def redo_action(request: UndoRedoRequest):
    """Redo the next action"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if not app_state.pipeline.can_redo():
            raise HTTPException(status_code=400, detail="Nothing to redo")

        # Perform redo
        app_state.pipeline.redo()

        # Broadcast updates
        await app_state.broadcast_chapter_update()
        await app_state.broadcast_history_update()

        return {"message": "Action redone"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to redo action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _format_timestamp_for_cue(seconds: float) -> str:
    """Format timestamp for CUE sheet format (MM:SS:FF where FF is frames)"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    frames = int((seconds % 1) * 75)  # 75 frames per second for audio CD
    return f"{minutes:02d}:{secs:02d}:{frames:02d}"


def _format_timestamp_readable(seconds: float) -> str:
    """Format timestamp in HH:MM:SS format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


@router.get("/chapters/export/csv")
async def export_chapters_csv():
    """Export selected chapters as CSV"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline or not app_state.pipeline.chapters:
            raise HTTPException(status_code=404, detail="No chapters found")

        # Filter selected chapters
        selected_chapters = [ch for ch in app_state.pipeline.chapters if ch.selected]

        if not selected_chapters:
            raise HTTPException(status_code=400, detail="No chapters selected for export")

        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["Chapter", "Timestamp", "Timestamp_Seconds", "Title"])

        # Write chapter data
        for idx, chapter in enumerate(selected_chapters):
            writer.writerow(
                [idx + 1, _format_timestamp_readable(chapter.timestamp), chapter.timestamp, chapter.current_title]
            )

        csv_content = output.getvalue()
        output.close()

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chapters_{timestamp}.csv"

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chapters/export/json")
async def export_chapters_json():
    """Export selected chapters as JSON"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline or not app_state.pipeline.chapters:
            raise HTTPException(status_code=404, detail="No chapters found")

        # Filter selected chapters
        selected_chapters = [ch for ch in app_state.pipeline.chapters if ch.selected]

        if not selected_chapters:
            raise HTTPException(status_code=400, detail="No chapters selected for export")

        # Create JSON structure
        chapters_data = {
            "export_timestamp": datetime.now().isoformat(),
            "total_chapters": len(selected_chapters),
            "chapters": [
                {
                    "chapter": idx + 1,
                    "timestamp": chapter.timestamp,
                    "timestamp_formatted": _format_timestamp_readable(chapter.timestamp),
                    "title": chapter.current_title,
                }
                for idx, chapter in enumerate(selected_chapters)
            ],
        }

        json_content = json.dumps(chapters_data, indent=2, ensure_ascii=False)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chapters_{timestamp}.json"

        return Response(
            content=json_content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export JSON: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chapters/export/cue")
async def export_chapters_cue():
    """Export selected chapters as CUE sheet"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline or not app_state.pipeline.chapters:
            raise HTTPException(status_code=404, detail="No chapters found")

        # Filter selected chapters
        selected_chapters = [ch for ch in app_state.pipeline.chapters if ch.selected]

        if not selected_chapters:
            raise HTTPException(status_code=400, detail="No chapters selected for export")

        # Create CUE sheet content
        cue_lines = []

        # CUE file header - we'll use generic values since we don't have audio file info
        cue_lines.append(f'TITLE "Audiobook Chapters"')
        cue_lines.append(f'PERFORMER "Unknown"')
        cue_lines.append(f'FILE "audiobook.mp3" MP3')
        cue_lines.append("")

        # Add tracks
        for idx, chapter in enumerate(selected_chapters):
            track_num = idx + 1
            cue_lines.append(f"  TRACK {track_num:02d} AUDIO")
            cue_lines.append(f'    TITLE "{chapter.current_title}"')
            cue_lines.append(f"    INDEX 01 {_format_timestamp_for_cue(chapter.timestamp)}")
            if idx < len(selected_chapters) - 1:
                cue_lines.append("")

        cue_content = "\n".join(cue_lines)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chapters_{timestamp}.cue"

        return Response(
            content=cue_content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export CUE: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chapters/add-options/{chapter_id}", response_model=AddOptionsResponse)
async def get_add_options(chapter_id: str):
    """Get available options for adding a chapter after the specified chapter"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        current_chapter = None
        chapters = [ch for ch in app_state.pipeline.chapters if not ch.deleted]

        for chapter in chapters:
            if chapter.id == chapter_id:
                current_chapter = chapter
                break

        if not current_chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")

        next_chapter = None
        current_found = False
        for chapter in sorted(chapters, key=lambda ch: ch.timestamp):
            if current_found and not chapter.deleted:
                next_chapter = chapter
                break
            if chapter.id == chapter_id:
                current_found = True

        min_timestamp_raw = current_chapter.timestamp
        max_timestamp_raw = (next_chapter.timestamp) if next_chapter else app_state.pipeline.book.duration

        min_timestamp = min_timestamp_raw + 1
        max_timestamp = max_timestamp_raw - 1

        detected_cues = []
        if app_state.pipeline.detected_silences:
            asr_buffer = app_state.pipeline.smart_detect_config.asr_buffer
            for silence_start, silence_end in app_state.pipeline.detected_silences:
                silence_end -= asr_buffer
                if min_timestamp < silence_end < max_timestamp:
                    detected_cues.append(DetectedCue(timestamp=silence_end, gap=silence_end - silence_start))
        else:
            logger.info("No preserved detection data available in pipeline")

        existing_cues = {}
        if app_state.pipeline.existing_cue_sources:
            for source in app_state.pipeline.existing_cue_sources:
                source_cues = []
                for cue in source.cues:
                    if min_timestamp < cue.timestamp < max_timestamp:
                        source_cues.append(ExistingCue(timestamp=cue.timestamp, title=cue.title or ""))
                if source_cues:
                    existing_cues[source.short_name] = source_cues

        deleted_chapters = []
        for chapter in app_state.pipeline.chapters:
            if chapter.deleted and min_timestamp < chapter.timestamp < max_timestamp:
                deleted_chapters.append(
                    DeletedChapter(timestamp=chapter.timestamp, title=chapter.current_title or chapter.asr_title or "")
                )

        return AddOptionsResponse(
            min_timestamp=min_timestamp_raw + 0.25,
            max_timestamp=max_timestamp_raw - 0.25,
            detected_cues=detected_cues,
            existing_cues=existing_cues,
            deleted=deleted_chapters,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get add options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chapters")
async def add_chapter(request: AddChapterRequest):
    """Add a new chapter at the specified timestamp"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        existing_deleted = None
        for chapter in app_state.pipeline.chapters:
            if chapter.deleted and abs(chapter.timestamp - request.timestamp) < 0.25:
                existing_deleted = chapter
                break

        operation: ChapterOperation = None

        if existing_deleted:
            operation = RestoreChapterOperation(chapter_id=existing_deleted.id)
            if request.title:
                operation.new_title = request.title

        else:
            from ...models.chapter import ChapterData
            operation = AddChapterOperation(
                chapter=ChapterData(
                    timestamp=request.timestamp,
                    asr_title="",
                    current_title=request.title or "",
                    selected=True,
                )
            )

        operation.apply(app_state.pipeline)
        app_state.pipeline.add_to_history(operation)

        await app_state.broadcast_chapter_update()
        await app_state.broadcast_history_update()

        return {"message": "Chapter added successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add chapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))
