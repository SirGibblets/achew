"""Session operations shared by the REST routes and the MCP server.

Each function holds the checks and side effects of one user action (open a book, add a
chapter, submit, cancel, ...) so the browser UI and an agent driving Achew over MCP go
through exactly the same code. A request the session can't satisfy raises
`SessionActionError`, an `HTTPException` so routes pass it straight through as their
response, which MCP tools turn into a tool error the agent can read.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.core.config import get_app_config
from app.core.constants import MIN_SEGMENT_GAP
from app.models.abs import AudnexusChapterList, BookSearchResult
from app.models.chapter import BasicChapter, ChapterData
from app.models.chapter_operation import (
    AddChapterOperation,
    BatchChapterOperation,
    ChapterOperation,
    RestoreChapterOperation,
    TranscribeOperation,
)
from app.models.enums import RestartStep, Step
from app.models.references import ChapterReference, ChapterRefType
from app.services.abs_service import ABSService
from app.services.audible_providers import region_for_provider

if TYPE_CHECKING:
    # The routes import this module, so their models can only be imported for typing
    from app.api.routes.chapters import DetectedCue
    from app.app import AppState
    from app.services.processing_pipeline import ProcessingPipeline

logger = logging.getLogger(__name__)

# A deleted chapter this close to a new chapter's timestamp is restored instead of
# adding a duplicate next to it.
RESTORE_TOLERANCE_SECONDS = 0.25

# Steps where the session has an active ffmpeg/VAD/ASR job, and where Cancel returns to
STEPS_CANCEL_TO_WORKFLOW = {Step.AUDIO_ANALYSIS, Step.VAD_PREP, Step.VAD_ANALYSIS, Step.REALIGN_VERIFICATION}
STEPS_CANCEL_TO_EDITING = {
    Step.AI_CLEANUP,
    Step.PARTIAL_SCAN_PREP,
    Step.PARTIAL_AUDIO_ANALYSIS,
    Step.PARTIAL_VAD_ANALYSIS,
}


class SessionActionError(HTTPException):
    """An action the current session can't perform, with the HTTP status the REST API answers with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(status_code=status, detail=message)
        self.message = message


def require_pipeline(app_state: "AppState") -> "ProcessingPipeline":
    if not app_state.pipeline:
        raise SessionActionError("Pipeline not found", status=404)
    return app_state.pipeline


def require_step(pipeline: "ProcessingPipeline", allowed: List[Step], action: str) -> None:
    if pipeline.step not in allowed:
        names = " or ".join(s.value for s in allowed)
        raise SessionActionError(f"Can only {action} during {names}. Current step: {pipeline.step.value}")


# ---------------------------------------------------------------------------
# Opening a book
# ---------------------------------------------------------------------------


async def fetch_and_announce(app_state: "AppState", pipeline: "ProcessingPipeline", item_id: str) -> None:
    """Download and prepare the book, then move every client to workflow selection.

    Raises whatever `fetch_item` raised; the pipeline has already been torn down (and
    clients sent back to the book search) by then.
    """
    result = await pipeline.fetch_item(item_id)
    logger.info(f"Fetched item: {result}")

    await app_state._broadcast_book_update()

    await app_state.broadcast_step_change(
        Step.SELECT_WORKFLOW,
        extras={
            "chapter_refs": pipeline.chapter_refs,
            "title_refs": pipeline.title_refs,
            "audio_xhe_aac": pipeline.audio_xhe_aac,
            "audio_unsupported_codec": pipeline.audio_unsupported_codec,
            "audio_info": pipeline.audio_info,
        },
    )


# ---------------------------------------------------------------------------
# Audnexus references
# ---------------------------------------------------------------------------

# Book search results enriched with Audnexus chapters, best match first
MAX_AUDNEXUS_CANDIDATES = 10


async def audnexus_candidates(
    provider: str, title: str = "", author: str = "", book_id: str = ""
) -> List[Tuple[BookSearchResult, AudnexusChapterList]]:
    """Search Audible (through ABS) and fetch Audnexus chapter data for the best matches.

    Results without an ASIN or without chapter data are dropped.
    """
    async with ABSService() as abs_service:
        results = await abs_service.search_books(provider=provider, title=title, author=author, book_id=book_id)
    if not results:
        return []

    results.sort(key=lambda r: r.matchConfidence or 0.0, reverse=True)
    results = results[:MAX_AUDNEXUS_CANDIDATES]
    region = region_for_provider(provider) or "US"

    async def enrich(result: BookSearchResult) -> Optional[Tuple[BookSearchResult, AudnexusChapterList]]:
        if not result.asin:
            return None
        try:
            async with ABSService() as svc:
                chapter_data = await svc.get_audnexus_chapters(result.asin, region=region)
        except Exception as e:
            logger.warning(f"Could not fetch Audnexus chapters for {result.asin}: {e}")
            return None
        if not chapter_data or not chapter_data.chapters:
            return None
        return result, chapter_data

    enriched = await asyncio.gather(*(enrich(r) for r in results))
    return [pair for pair in enriched if pair is not None]


async def fetch_audnexus_reference(asin: str, provider: str = "audible") -> ChapterReference:
    """Build a Chapter Reference from the Audnexus chapter data for `asin`."""
    region = region_for_provider(provider) or "US"
    async with ABSService() as abs_service:
        chapter_data = await abs_service.get_audnexus_chapters(asin, region=region)

    if not chapter_data or not chapter_data.chapters:
        raise SessionActionError(f"No Audnexus chapter data found for ASIN {asin}", status=404)

    chapters = [BasicChapter(timestamp=ch.startOffsetMs / 1000, title=ch.title) for ch in chapter_data.chapters]
    duration_sec = float(chapter_data.runtimeLengthMs) / 1000
    return ChapterReference(
        type=ChapterRefType.AUDNEXUS,
        name="Audnexus Chapters",
        short_name="Audnexus",
        description=f"Audnexus chapter data for ASIN {asin}",
        metadata={
            "ASIN": asin,
            "Duration": f"{int(duration_sec // 60)}m",
        },
        chapters=chapters,
        duration=duration_sec,
    )


# ---------------------------------------------------------------------------
# Initial chapter selection / transcription setup
# ---------------------------------------------------------------------------


def validate_initial_selection(
    pipeline: "ProcessingPipeline", timestamps: List[float], include_unaligned: List[str]
) -> None:
    if pipeline.step != Step.INITIAL_CHAPTER_SELECTION:
        raise SessionActionError("Pipeline not in initial chapter selection step")
    if not timestamps:
        raise SessionActionError("At least one timestamp is required")
    available_ref_ids = [ref.id for ref in pipeline.chapter_refs]
    for option in include_unaligned:
        if option not in available_ref_ids:
            raise SessionActionError(
                f"Invalid include_unaligned option: {option}. Available options: {available_ref_ids}"
            )


def validate_preassigned_titles(pipeline: "ProcessingPipeline", items: List[Tuple[int, str]]) -> Dict[int, str]:
    """Check (cue_index, title) pairs against the selected cues and build the index -> title map."""
    cue_count = len(pipeline.cues)
    preassigned: Dict[int, str] = {}
    for cue_index, title in items:
        if cue_index < 0 or cue_index >= cue_count:
            raise SessionActionError(f"preassigned_titles cue_index {cue_index} out of range [0, {cue_count})")
        if cue_index in preassigned:
            raise SessionActionError(f"preassigned_titles contains duplicate cue_index {cue_index}")
        preassigned[cue_index] = title
    return preassigned


# ---------------------------------------------------------------------------
# Chapter editing
# ---------------------------------------------------------------------------


def build_add_chapter_operation(
    pipeline: "ProcessingPipeline", timestamp: float, title: str = "", transcript: Optional[str] = None
) -> Tuple[ChapterOperation, str]:
    """The undoable operation that adds a chapter at `timestamp`, and the new chapter's id.

    A deleted chapter at (nearly) the same timestamp is restored rather than duplicated.
    A supplied transcript also becomes the title, in the same undo step.
    """
    existing_deleted = next(
        (c for c in pipeline.chapters if c.deleted and abs(c.timestamp - timestamp) < RESTORE_TOLERANCE_SECONDS),
        None,
    )

    operation: ChapterOperation
    if existing_deleted:
        restore_op = RestoreChapterOperation(chapter_id=existing_deleted.id)
        if title:
            restore_op.new_title = title
        operation = restore_op
        chapter_id = existing_deleted.id
    else:
        new_chapter = ChapterData(timestamp=timestamp, title=title or "")
        new_chapter.selected = True
        operation = AddChapterOperation(chapter=new_chapter)
        chapter_id = new_chapter.id

    if transcript is not None:
        # Same result as the transcription worker, but as one undo step with the add
        transcribe_op = TranscribeOperation(chapter_id=chapter_id, new_transcript=transcript, new_title=transcript)
        operation = BatchChapterOperation(operations=[operation, transcribe_op])

    return operation, chapter_id


def nearby_cues(pipeline: "ProcessingPipeline", chapter_id: str) -> List["DetectedCue"]:
    """Detected cues between the chapters either side of `chapter_id` (the places it could move to)."""
    require_step(pipeline, [Step.CHAPTER_EDITING], "fetch nearby cues")
    if not pipeline.book:
        raise SessionActionError("Book not found", status=404)

    chapters = sorted([ch for ch in pipeline.chapters if not ch.deleted], key=lambda ch: ch.timestamp)
    current_index = next((i for i, ch in enumerate(chapters) if ch.id == chapter_id), -1)
    if current_index == -1:
        raise SessionActionError("Chapter not found", status=404)

    prev_chapter = chapters[current_index - 1] if current_index > 0 else None
    next_chapter = chapters[current_index + 1] if current_index < len(chapters) - 1 else None

    min_timestamp = (prev_chapter.timestamp if prev_chapter else 0.0) + 1
    max_timestamp = (next_chapter.timestamp if next_chapter else pipeline.book.duration) - 1

    return [cue for cue in pipeline.detected_cues if min_timestamp < cue.timestamp < max_timestamp]


def snippet_duration(pipeline: "ProcessingPipeline", timestamp: float) -> float:
    """How much audio a transcript preview at `timestamp` covers: the ASR segment length,
    clipped to the next chapter so it doesn't run into it."""
    require_step(pipeline, [Step.CHAPTER_EDITING], "transcribe snippets")

    duration_limit = pipeline.book.duration if pipeline.book else timestamp + 1e9
    next_timestamps = [
        c.timestamp for c in pipeline.chapters if not c.deleted and c.timestamp > timestamp + MIN_SEGMENT_GAP
    ]
    if next_timestamps:
        duration_limit = min(duration_limit, min(next_timestamps) - MIN_SEGMENT_GAP)
    duration = min(get_app_config().asr_options.segment_length, duration_limit - timestamp)
    if duration <= 0:
        raise SessionActionError("No audio available at this timestamp")
    return duration


# ---------------------------------------------------------------------------
# Submit / cancel
# ---------------------------------------------------------------------------


async def submit_to_abs(app_state: "AppState", pipeline: "ProcessingPipeline") -> None:
    """Write the selected chapters to Audiobookshelf and finish the session (step COMPLETED).

    On failure the session moves to REVIEWING so nothing is lost, and this raises.
    """
    require_step(pipeline, [Step.CHAPTER_EDITING, Step.REVIEWING], "submit")

    if await pipeline.submit_chapters(pipeline.chapters):
        pipeline.step = Step.COMPLETED
        await app_state.broadcast_step_change(Step.COMPLETED)
        return

    pipeline.step = Step.REVIEWING
    await app_state.broadcast_step_change(Step.REVIEWING)
    raise SessionActionError("Failed to submit chapters", status=500)


async def cancel_current_step(app_state: "AppState") -> Dict[str, str]:
    """Stop the running step and go back to the last interactive one."""
    pipeline = require_pipeline(app_state)
    step = pipeline.step

    if step in [Step.VALIDATING, Step.DOWNLOADING]:
        if not await app_state.delete_pipeline():
            raise SessionActionError("Pipeline not found", status=404)
        return {"message": "Pipeline cancelled and deleted", "action": "deleted"}

    if step in STEPS_CANCEL_TO_WORKFLOW:
        restart_step = RestartStep.SELECT_WORKFLOW
        message = "Processing cancelled, returned to workflow selection"
    elif step == Step.AUDIO_EXTRACTION:
        restart_step = RestartStep.SELECT_WORKFLOW if pipeline.is_realignment else RestartStep.CONFIGURE_ASR
        message = f"Audio extraction cancelled, returned to {restart_step.value}"
    elif step in [Step.TRIMMING, Step.ASR_PROCESSING]:
        restart_step = RestartStep.CONFIGURE_ASR
        message = "Transcription process cancelled, returned to ASR configuration"
    elif step in STEPS_CANCEL_TO_EDITING:
        restart_step = RestartStep.CHAPTER_EDITING
        message = "Processing cancelled, returned to chapter editing"
    else:
        restart_step = RestartStep.SELECT_WORKFLOW
        message = "Processing cancelled, returned to workflow selection"

    await pipeline.restart_at_step(restart_step)
    return {"message": message, "action": "restarted", "restart_step": restart_step.value}
