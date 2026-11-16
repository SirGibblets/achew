"""MCP tools for the chapter editor: listing and editing chapters, checking boundaries by
transcription and detected cues, re-running realignment, undo/redo, and submitting."""

import re
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple, Union

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ToolAnnotations
from pydantic import BaseModel, Field

from app.app import get_app_state
from app.core.config import get_app_config
from app.core.constants import MIN_SEGMENT_GAP
from app.models.chapter import ChapterData
from app.models.chapter_operation import (
    BatchChapterOperation,
    ChapterOperation,
    DeleteChapterOperation,
    EditTimestampOperation,
    EditTitleOperation,
    SetPinnedOperation,
    TranscribeOperation,
)
from app.models.enums import Step
from app.models.references import ChapterRefType
from app.services.asr_service import ASRFatalError
from app.services.asr_service_options import get_preferred_service
from app.services.session_actions import (
    build_add_chapter_operation,
    nearby_cues,
    snippet_duration,
    submit_to_abs,
)
from app.services.title_matching import normalize

from .runtime import (
    BEYOND_AUDIO_MARGIN_SECONDS,
    CUE_TIME_NOTE,
    DEFAULT_WAIT_SECONDS,
    EDITS,
    MAX_WAIT_SECONDS,
    READ_ONLY,
    TimeArg,
    active_chapters,
    announced_heading,
    busy_reason,
    chapter_views,
    coverage,
    cue_view,
    fmt_duration,
    fmt_time,
    in_window,
    need_pipeline,
    need_step,
    parse_time,
    pauses_between,
    quote,
    resolve_chapter,
    result,
    session_warnings,
    settle,
    short_id,
    snapshot,
    titles_from_transcripts,
    tool_errors,
    transcript_matches_title,
)

Timeout = Annotated[
    float,
    Field(ge=0, le=MAX_WAIT_SECONDS, description="Seconds to wait for the work to finish before returning"),
]

# Two chapters can't start closer together than this
MIN_CHAPTER_SPACING_SECONDS = 0.25

# get_nearby_cues lists this many cues nearest the chapter's start by default (a long chapter's
# span can hold hundreds)
DEFAULT_NEARBY_CUES = 30

# Moving a chapter at least this far clears its transcript, which was heard at the old start
MOVE_CLEARS_TRANSCRIPT_SECONDS = 1.0

# edit_chapters lists each change and the chapters it touched for batches up to
# MAX_ECHOED_CHANGES; bigger ones get per-action counts and the first ECHOED_SAMPLE changes
MAX_ECHOED_CHANGES = 20
ECHOED_SAMPLE = 5

# transcribe_audio limits: snippets per call, and the longest snippet
MAX_SNIPPETS = 10
MAX_SNIPPET_SECONDS = 30.0
MIN_SNIPPET_SECONDS = 1.0

# transcribe_audio: how far before each point a snippet may start, how close a detected cue
# must be to a chapter's start to count as the silence before it, and the share of the book
# after which an extraction failure is likely the file ending early
MAX_LEAD_SECONDS = 10.0

# Default listening window when the user's transcription length is shorter: clips of a few
# seconds come back as noise ("[Music]", a stray syllable) where longer ones transcribe cleanly
MIN_DEFAULT_SNIPPET_SECONDS = 15.0
SILENCE_MATCH_SECONDS = 1.0
NEAR_END_FRACTION = 0.95

# Steps with a loaded book and nothing running, where snippets can be transcribed
SNIPPET_STEPS = [
    Step.SELECT_WORKFLOW,
    Step.INITIAL_CHAPTER_SELECTION,
    Step.CONFIGURE_ASR,
    Step.CHAPTER_EDITING,
    Step.REVIEWING,
]

# preview_submission pairs new chapters with current ones within MATCH_TOLERANCE_SECONDS,
# then (unpaired by title too) within REMATCH_WINDOW_SECONDS; a paired chapter counts as
# moved once its start changed by MOVE_THRESHOLD_SECONDS. Chapters shorter than
# SHORT_CHAPTER_SECONDS are flagged.
MATCH_TOLERANCE_SECONDS = 2.0
REMATCH_WINDOW_SECONDS = 120.0
MOVE_THRESHOLD_SECONDS = 0.5
SHORT_CHAPTER_SECONDS = 10.0
MAX_LISTED_CHANGES = 60

# Chapters that are short by nature and never warned about: credits and announcements
EXPECTED_SHORT_TITLE_RE = re.compile(r"\b(credits?|intro|outro|introduction|dedication|epigraph)\b", re.IGNORECASE)

# A short chapter that a reference also has as a short chapter (under this length) is expected,
# not a mistake: part headings, epigraphs. Those are reported as one group.
REFERENCE_SHORT_SECONDS = 2 * SHORT_CHAPTER_SECONDS

SUBMIT = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True)


class ChapterChange(BaseModel):
    """One edit in an edit_chapters batch."""

    action: Literal["rename", "move", "delete", "add", "pin", "unpin"] = Field(
        description="rename: set the title. move: set where it starts. delete: remove it (a deleted chapter can "
        "be brought back by adding one at its start). add: a new chapter. pin/unpin: mark a realigned chapter's "
        "start as confirmed, so realign_unpinned leaves it alone and aligns the rest around it."
    )
    id: Optional[str] = Field(default=None, description="The chapter's id from list_chapters (all but add)")
    title: Optional[str] = Field(default=None, description="rename: the new title. add: the new chapter's title")
    start: Optional[Union[float, str]] = Field(
        default=None, description="move/add: where the chapter starts, in seconds or h:mm:ss"
    )


def _check_start(pipeline, t: float, moving: Optional[ChapterData] = None) -> None:
    duration = pipeline.book_duration
    if not 0 <= t < duration:
        raise ValueError(f"{fmt_time(t)} is outside the book (0:00:00 to {fmt_time(duration)})")
    for other in pipeline.chapters:
        if other.deleted or other is moving:
            continue
        if abs(other.timestamp - t) < MIN_CHAPTER_SPACING_SECONDS:
            raise ValueError(f"Chapter {short_id(other)} ({quote(other.title)}) already starts at {fmt_time(t)}")


def _build_operation(pipeline, change: ChapterChange) -> Tuple[ChapterOperation, str, str]:
    """The operation for one change, a description of it, and the id of the chapter it touches."""
    if change.action == "add":
        if change.start is None:
            raise ValueError("add needs start")
        t = parse_time(change.start)
        _check_start(pipeline, t)
        title = (change.title or "").strip()
        operation, chapter_id = build_add_chapter_operation(pipeline, t, title)
        restored = next((c for c in pipeline.chapters if c.id == chapter_id and c.deleted), None)
        if restored is None:
            return operation, f"added {quote(title)} at {fmt_time(t)}", chapter_id
        # Adding at a deleted chapter's start brings that chapter back. The agent chose this
        # start, so set it exactly and confirm it: a realigned chapter is pinned, no longer a guess.
        confirm = EditTimestampOperation(chapter_id=chapter_id, new_timestamp=t)
        description = (
            f"restored deleted chapter {short_id(restored)} ({quote((title or restored.title))}) at {fmt_time(t)}"
        )
        if restored.realignment is not None:
            description += ", confirmed and pinned"
        return BatchChapterOperation(operations=[operation, confirm]), description, chapter_id

    if not change.id:
        raise ValueError(f"{change.action} needs the chapter id")
    chapter = resolve_chapter(pipeline.chapters, change.id)
    label = f"{short_id(chapter)} ({quote(chapter.title)})"

    if change.action == "rename":
        title = (change.title or "").strip()
        if not title:
            raise ValueError(f"rename of {label} needs a non-empty title")
        return (
            EditTitleOperation(chapter_id=chapter.id, new_title=title),
            f"renamed {label} to {quote(title)}",
            chapter.id,
        )
    if change.action == "move":
        if change.start is None:
            raise ValueError(f"move of {label} needs start")
        t = parse_time(change.start)
        _check_start(pipeline, t, moving=chapter)
        description = f"moved {label} from {fmt_time(chapter.timestamp)} to {fmt_time(t)}"
        move = EditTimestampOperation(chapter_id=chapter.id, new_timestamp=t)
        if not chapter.transcript or abs(t - chapter.timestamp) < MOVE_CLEARS_TRANSCRIPT_SECONDS:
            return move, description, chapter.id
        # What was heard at the old start doesn't describe the new one; transcribe_audio hears it
        clear = TranscribeOperation(chapter_id=chapter.id, new_transcript="", new_title=chapter.title)
        return (
            BatchChapterOperation(operations=[move, clear]),
            description + " and cleared its old transcript",
            chapter.id,
        )
    if change.action == "delete":
        return DeleteChapterOperation(chapter_id=chapter.id), f"deleted {label}", chapter.id
    # pin / unpin
    if chapter.realignment is None:
        raise ValueError(f"{label} wasn't realigned, so it can't be pinned")
    pinned = change.action == "pin"
    return SetPinnedOperation(chapter_id=chapter.id, pinned=pinned), f"{change.action}ned {label}", chapter.id


def _snippet_seconds(pipeline, t: float, seconds: Optional[float]) -> float:
    remaining = pipeline.book_duration - t
    if seconds is not None:
        return max(MIN_SNIPPET_SECONDS, min(seconds, MAX_SNIPPET_SECONDS, remaining))
    default = max(get_app_config().asr_options.segment_length, MIN_DEFAULT_SNIPPET_SECONDS)
    if pipeline.step == Step.CHAPTER_EDITING:
        # Up to the next chapter, so a short chapter (a heading, an epigraph) is heard whole
        next_starts = [c.timestamp for c in pipeline.chapters if not c.deleted and c.timestamp > t + MIN_SEGMENT_GAP]
        to_next = min([*next_starts, pipeline.book_duration]) - MIN_SEGMENT_GAP - t
        if 0 < to_next <= MAX_SNIPPET_SECONDS:
            return to_next
        if to_next > 0:
            return min(default, to_next)
        return snippet_duration(pipeline, t)
    return min(default, remaining)


def _silence_before(pipeline, start: float) -> Any:
    """The detected silence that ends at a chapter's start (a cue within SILENCE_MATCH_SECONDS of
    it), or why there's none."""
    cue = min(pipeline.detected_cues, key=lambda c: abs(c.timestamp - start), default=None)
    if cue is not None and abs(cue.timestamp - start) <= SILENCE_MATCH_SECONDS:
        view = cue_view(cue)
        return {"gap": view["gap"], "silence_from": view["silence_from"]}
    if coverage(pipeline, start - SILENCE_MATCH_SECONDS, start + SILENCE_MATCH_SECONDS)["scanned_percent"] < 100:
        return "not scanned for silences here"
    return "none detected"


def _norm_title(title: str) -> str:
    return re.sub(r"\W+", " ", title.lower()).strip()


def _current_abs_chapters(pipeline) -> List[Tuple[float, str]]:
    """The chapters Audiobookshelf had when the book was opened."""
    abs_ref = next((r for r in pipeline.chapter_refs if r.type == ChapterRefType.ABS), None)
    if abs_ref is not None:
        return [(c.timestamp, c.title) for c in abs_ref.chapters]
    if pipeline.book:
        return [(c.start, c.title) for c in pipeline.book.media.chapters]
    return []


def _short_in_a_reference(pipeline, chapter: ChapterData) -> bool:
    """Whether a reference also has this short chapter (a part heading or epigraph the publisher
    lists too), by title or by a short reference chapter at its start."""
    title = normalize(chapter.title)
    starts = {chapter.timestamp}
    if chapter.realignment is not None:
        starts.add(chapter.realignment.original_timestamp)
    for ref in pipeline.chapter_refs:
        for i, ref_chapter in enumerate(ref.chapters):
            ref_end = ref.chapters[i + 1].timestamp if i + 1 < len(ref.chapters) else ref.duration
            if ref_end - ref_chapter.timestamp >= REFERENCE_SHORT_SECONDS:
                continue
            if (title and normalize(ref_chapter.title) == title) or any(
                abs(ref_chapter.timestamp - t) <= MATCH_TOLERANCE_SECONDS for t in starts
            ):
                return True
    return False


def _diff(
    final: List[Tuple[float, str]], current: List[Tuple[float, str]], max_listed: Optional[int]
) -> Tuple[Dict[str, Any], set]:
    """Compare the chapters to be written with the ones Audiobookshelf has now. Returns the
    counts and changes, and the indices of the new chapters with no counterpart.

    Each new chapter is paired with a current one: first by start time, then by title, then
    by nearest start within REMATCH_WINDOW_SECONDS. A paired chapter can be both moved and
    retitled; unpaired ones are added or removed. Added chapters aren't listed as changes,
    since the preview's chapter list marks them.
    """
    unmatched = list(range(len(current)))
    pairs: List[Tuple[int, int]] = []
    leftovers = list(range(len(final)))

    def pair_pass(match) -> None:
        for f in list(leftovers):
            c = match(f)
            if c is not None:
                unmatched.remove(c)
                leftovers.remove(f)
                pairs.append((f, c))

    def by_start(f: int, window: float) -> Optional[int]:
        c = min(unmatched, key=lambda i: abs(current[i][0] - final[f][0]), default=None)
        return c if c is not None and abs(current[c][0] - final[f][0]) <= window else None

    pair_pass(lambda f: by_start(f, MATCH_TOLERANCE_SECONDS))
    pair_pass(lambda f: next((c for c in unmatched if _norm_title(current[c][1]) == _norm_title(final[f][1])), None))
    pair_pass(lambda f: by_start(f, REMATCH_WINDOW_SECONDS))

    counts = {"unchanged": 0, "moved": 0, "retitled": 0, "added": len(leftovers), "removed": len(unmatched)}
    changes: List[Tuple[float, str]] = []
    for f, c in sorted(pairs):
        (t, title), (old_t, old_title) = final[f], current[c]
        moved = abs(t - old_t) >= MOVE_THRESHOLD_SECONDS
        retitled = title != old_title
        counts["moved"] += moved
        counts["retitled"] += retitled
        counts["unchanged"] += not moved and not retitled
        if moved or retitled:
            parts = [f"{fmt_time(old_t)} -> {fmt_time(t)} ({t - old_t:+.1f} s)" if moved else fmt_time(t)]
            parts.append(f"{quote(old_title)} -> {quote(title)}" if retitled else quote(title))
            changes.append((t, ": ".join(parts)))
    changes += [(current[c][0], f"removed {fmt_time(current[c][0])}: {quote(current[c][1])}") for c in unmatched]

    listed = [text for _, text in sorted(changes)][:max_listed]
    if len(changes) > len(listed):
        listed.append(f"... and {len(changes) - len(listed)} more")
    return {**counts, "changes": listed or None}, set(leftovers)


def register(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY)
    @tool_errors
    async def list_chapters(
        transcripts: Annotated[
            Literal["differing", "all", "none"],
            Field(
                description="differing: show a chapter's transcript only where it doesn't match its title. all: "
                "always show it. none: leave transcripts out"
            ),
        ] = "differing",
        include_deleted: Annotated[bool, Field(description="Also list deleted chapters")] = False,
    ) -> CallToolResult:
        """The open book's chapters in the editor: id (for edit_chapters), start, length, title, and for
        realigned books the aligner's confidence (`guess: true` means no strong cue confirmed it) and whether it's
        pinned. `excluded` chapters stay in the editor but aren't written to Audiobookshelf. `beyond_audio`
        chapters start at or after the end of the recording.

        Transcripts: a chapter whose start was transcribed has `transcript_matches` (true when what was heard
        announces the title, allowing for "Two" vs "2", a section's number alone for "Chapter 1.2", and extra
        words after it), or `title_is_transcript` when its title still is the raw transcript (as after
        transcription titling, before you rename it). A chapter with neither was never transcribed.

        `suspect` marks chapters that look wrong, with a reason and where to look: e.g. a "Chapter N" heading
        that runs for minutes when the book's other headings are seconds long has swallowed its first section."""
        app_state = get_app_state()
        pipeline = need_pipeline(app_state)
        if not [c for c in pipeline.chapters if not c.deleted]:
            raise ToolError(f"There are no chapters yet (step {pipeline.step.value}). {snapshot(app_state)['next']}")
        active = active_chapters(pipeline.chapters)
        data: Dict[str, Any] = {
            "step": pipeline.step.value,
            "book_length": fmt_duration(pipeline.book_duration),
            "transcribed": f"{sum(1 for c in active if c.transcript)} of {len(active)} chapters",
            "audio_files": len(pipeline.file_starts)
            if pipeline.file_starts and len(pipeline.file_starts) > 1
            else None,
            "warnings": session_warnings(pipeline) or None,
            "chapters": chapter_views(
                pipeline.chapters,
                pipeline.book_duration,
                transcripts,
                cues=pipeline.detected_cues,
                from_transcripts=titles_from_transcripts(pipeline),
                file_starts=pipeline.file_starts,
            ),
        }
        if include_deleted:
            data["deleted"] = [
                {"id": short_id(c), "time": fmt_time(c.timestamp), "title": c.title or c.transcript}
                for c in sorted(pipeline.chapters, key=lambda c: c.timestamp)
                if c.deleted
            ]
        return result(data)

    @server.tool(annotations=EDITS)
    @tool_errors
    async def edit_chapters(
        changes: Annotated[List[ChapterChange], Field(min_length=1, description="Edits, applied in order")],
    ) -> CallToolResult:
        """Rename, move, delete, add, pin or unpin chapters, all as one step the user can undo with a single
        Undo in the web UI. If any change is invalid, none are applied. Moving a realigned chapter also pins it.
        Prefer one call with every change over many small calls. Batches over 20 changes are answered with
        counts per action instead of every change (check the result with list_chapters)."""
        app_state = get_app_state()
        need_step(app_state, [Step.CHAPTER_EDITING], "edit chapters")
        pipeline = need_pipeline(app_state)

        applied: List[ChapterOperation] = []
        descriptions: List[str] = []
        touched: List[str] = []
        try:
            for i, change in enumerate(changes):
                try:
                    operation, description, chapter_id = _build_operation(pipeline, change)
                    operation.apply(pipeline)
                except ValueError as e:
                    raise ValueError(f"Change {i + 1} ({change.action}): {e}") from e
                applied.append(operation)
                descriptions.append(description)
                touched.append(chapter_id)
            if not active_chapters(pipeline.chapters):
                raise ValueError("These changes would leave the book with no chapters")
        except Exception:
            for operation in reversed(applied):
                operation.undo(pipeline)
            raise

        pipeline.add_to_history(BatchChapterOperation(operations=applied))
        await app_state.broadcast_chapter_update()
        await app_state.broadcast_history_update()

        data: Dict[str, Any] = {
            "chapters_now": len(active_chapters(pipeline.chapters)),
            "warnings": session_warnings(pipeline) or None,
        }
        if len(changes) <= MAX_ECHOED_CHANGES:
            data["applied"] = descriptions
            data["changed"] = (
                chapter_views(
                    pipeline.chapters,
                    pipeline.book_duration,
                    only_ids=set(touched),
                    from_transcripts=titles_from_transcripts(pipeline),
                )
                or None
            )
        else:
            # A big batch (a whole book's renames) is summarised; list_chapters shows the result
            counts: Dict[str, int] = {}
            for change in changes:
                counts[change.action] = counts.get(change.action, 0) + 1
            data["applied"] = counts
            data["first_changes"] = descriptions[:ECHOED_SAMPLE]
        return result(data)

    @server.tool(annotations=EDITS)
    @tool_errors
    async def set_chapter_selection(
        selected: Annotated[bool, Field(description="false excludes the chapters from what gets submitted")],
        chapter_ids: Annotated[Optional[List[str]], Field(description="Chapters to change; omit for all")] = None,
    ) -> CallToolResult:
        """Include or exclude chapters from submission without deleting them (the editor's checkboxes; not
        undoable). AI Cleanup in the web UI excludes chapters it thinks aren't real; check for `excluded`
        chapters before submitting. To get rid of a chapter, prefer delete in edit_chapters."""
        app_state = get_app_state()
        need_step(app_state, [Step.CHAPTER_EDITING], "change chapter selection")
        pipeline = need_pipeline(app_state)
        if chapter_ids is None:
            targets = active_chapters(pipeline.chapters)
        else:
            targets = [resolve_chapter(pipeline.chapters, ref) for ref in chapter_ids]
        changed = 0
        for chapter in targets:
            if chapter.selected != selected:
                chapter.selected = selected
                changed += 1
        if changed:
            await app_state.broadcast_chapter_update()
        return result({"changed": changed, "selected" if selected else "excluded": len(targets)})

    @server.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_nearby_cues(
        chapter_id: Annotated[str, Field(description="The chapter's id from list_chapters")],
        from_time: Annotated[TimeArg, Field(description="Only cues from this time (seconds or h:mm:ss)")] = None,
        to_time: Annotated[TimeArg, Field(description="Only cues up to this time (seconds or h:mm:ss)")] = None,
        min_gap_seconds: Annotated[
            Optional[float], Field(ge=0, description="Only cues with at least this much silence")
        ] = None,
        max_cues: Annotated[
            int, Field(ge=1, le=500, description="List at most this many, nearest the chapter's start first")
        ] = DEFAULT_NEARBY_CUES,
    ) -> CallToolResult:
        """Detected silences (cues) between the chapters before and after this one: the places its start could
        move to. Lists the max_cues nearest its current start (in time order), each with its offset from that
        start and its silence length; `total_matching` says how many there are in all. A cue marks where
        speech resumes after the silence, so the silence comes before its time. Narrow long spans with
        from_time/to_time or min_gap_seconds. `scanned` says how much of the span Achew has looked for
        silences in (realignment only scans near the reference's starts): where it hasn't, try scan_for_cues."""
        app_state = get_app_state()
        pipeline = need_pipeline(app_state)
        chapter = resolve_chapter(pipeline.chapters, chapter_id)
        cues = [
            c
            for c in in_window(nearby_cues(pipeline, chapter.id), from_time, to_time)
            if min_gap_seconds is None or c.gap >= min_gap_seconds
        ]
        listed = sorted(cues, key=lambda c: abs(c.timestamp - chapter.timestamp))[:max_cues]
        listed.sort(key=lambda c: c.timestamp)
        ordered = active_chapters(pipeline.chapters)
        index = ordered.index(chapter)
        span_start = ordered[index - 1].timestamp if index > 0 else 0.0
        span_end = ordered[index + 1].timestamp if index + 1 < len(ordered) else pipeline.book_duration
        if from_time is not None:
            span_start = max(span_start, parse_time(from_time))
        if to_time is not None:
            span_end = min(span_end, parse_time(to_time))
        return result(
            {
                "chapter": {"id": short_id(chapter), "time": fmt_time(chapter.timestamp), "title": chapter.title},
                "scanned": coverage(pipeline, span_start, span_end),
                "total_matching": len(cues),
                "listed": f"the {len(listed)} nearest" if len(listed) < len(cues) else None,
                "cues": [cue_view(c, chapter.timestamp) for c in listed],
                "note": CUE_TIME_NOTE,
            }
        )

    @server.tool(annotations=READ_ONLY)
    @tool_errors
    async def transcribe_audio(
        ctx: Context,
        timestamps: Annotated[
            Optional[List[Union[float, str]]],
            Field(max_length=MAX_SNIPPETS, description="Where to listen, in seconds or h:mm:ss"),
        ] = None,
        chapter_ids: Annotated[
            Optional[List[str]],
            Field(
                max_length=MAX_SNIPPETS,
                description="Chapters to check instead: listens at each one's start and reports whether its title "
                "was heard and the silence before it",
            ),
        ] = None,
        seconds: Annotated[
            Optional[float],
            Field(
                ge=MIN_SNIPPET_SECONDS,
                le=MAX_SNIPPET_SECONDS,
                description="How much audio to transcribe from each point. Defaults to the user's transcription "
                "length (at least 15 s), stopping at the next chapter; in the editor, a chapter under 30 s is heard "
                "whole. Clips under ~10 s often transcribe as noise",
            ),
        ] = None,
        lead_seconds: Annotated[
            float,
            Field(
                ge=0,
                le=MAX_LEAD_SECONDS,
                description="Start each snippet this much earlier, to also hear the end of what comes before",
            ),
        ] = 0.0,
        trim: Annotated[
            bool,
            Field(
                description="Cut each snippet at its longest pause first, as chapter transcription does to isolate "
                "a title. Off by default, so you hear the whole window"
            ),
        ] = False,
    ) -> CallToolResult:
        """Hear what's said at points in the book: transcribe a few seconds of audio from each timestamp, or at
        each chapter's start (chapter_ids). Use it to check that a chapter starts where its title is read, or to
        identify an unclear title. With chapter_ids, each snippet says whether the title was heard
        (`title_heard`, anywhere in the snippet, ignoring track numbers like "01 - ") and the detected silence
        before the start (`silence_before`). `announces` gives the chapter heading a snippet announces
        ("Chapter 5" from "Chapter 5 of Oliver Twist. This LibriVox recording..."). Doesn't change anything.
        The first call may take a while as the transcription model loads.

        Each snippet lists the `pauses` Achew detected inside it. Speech after a long pause may be missing from a
        transcript (always, with trim): listen again from after the pause before concluding nothing is said."""
        app_state = get_app_state()
        need_step(app_state, SNIPPET_STEPS, "transcribe audio")
        pipeline = need_pipeline(app_state)
        reason = busy_reason(app_state)
        if reason:
            raise ToolError(f"Can't transcribe while Achew is busy ({reason}). Call wait first.")
        if get_preferred_service() is None:
            raise ToolError("No transcription service is set up (Settings → Transcription Settings in the web UI).")
        if bool(timestamps) == bool(chapter_ids):
            raise ToolError("Pass either timestamps or chapter_ids")

        points: List[Tuple[float, Optional[ChapterData]]] = []
        for value in timestamps or []:
            points.append((parse_time(value), None))
        for ref in chapter_ids or []:
            chapter = resolve_chapter(pipeline.chapters, ref)
            points.append((chapter.timestamp, chapter))

        snippets = []
        for i, (point, chapter) in enumerate(points):
            if not 0 <= point < pipeline.book_duration:
                raise ToolError(
                    f"{fmt_time(point)} is outside the book (0:00:00 to {fmt_time(pipeline.book_duration)})"
                )
            start = max(0.0, point - lead_seconds)
            duration = min(_snippet_seconds(pipeline, point, seconds) + (point - start), pipeline.book_duration - start)
            try:
                await ctx.report_progress(float(i), float(len(points)), f"Transcribing {fmt_time(point)}")
            except Exception:
                pass
            error = None
            try:
                transcript = await app_state.transcribe_snippet(start, duration, label=f"mcp_{i}", trim=trim)
            except ASRFatalError as e:
                raise ToolError(f"Transcription failed: {e}") from e
            except Exception as e:
                # Pass the service's own reason through, rather than a generic tool failure
                transcript, error = None, f"Transcription failed: {type(e).__name__}: {e}"
            if transcript is None and error is None:
                error = "Couldn't extract audio here."
                if point >= pipeline.book_duration * NEAR_END_FRACTION:
                    error += " This is near the end: the file may be shorter than its reported length."
            pauses = pauses_between(pipeline.detected_cues, start, start + duration)
            snippet: Dict[str, Any] = {
                "start": round(start, 2),
                "time": fmt_time(start),
                "seconds": round(duration, 1),
                "transcript": transcript.strip() if transcript is not None else None,
                "pauses": pauses or None,
                "trimmed_at_longest_pause": True if trim and pauses else None,
                "error": error,
            }
            snippet["announces"] = announced_heading(transcript) if transcript else None
            if chapter is not None:
                snippet["chapter"] = {"id": short_id(chapter), "title": chapter.title}
                snippet["title_heard"] = (
                    transcript_matches_title(chapter.title, transcript) if transcript is not None else None
                )
                snippet["silence_before"] = _silence_before(pipeline, chapter.timestamp)
            snippets.append(snippet)
        return result({"snippets": snippets})

    @server.tool(annotations=EDITS)
    @tool_errors
    async def transcribe_chapters(
        ctx: Context,
        chapter_ids: Annotated[
            Optional[List[str]], Field(description="Chapters to transcribe; omit for every included chapter")
        ] = None,
        timeout_seconds: Timeout = DEFAULT_WAIT_SECONDS,
    ) -> CallToolResult:
        """Transcribe the start of chapters and replace their titles with what's heard (one undo step), like the
        editor's Transcribe button. Useful before rewriting titles yourself; to just listen without changing
        titles, use transcribe_audio."""
        app_state = get_app_state()
        need_step(app_state, [Step.CHAPTER_EDITING], "transcribe chapters")
        pipeline = need_pipeline(app_state)
        if get_preferred_service() is None:
            raise ToolError("No transcription service is set up (Settings → Transcription Settings in the web UI).")
        if app_state.has_active_transcriptions:
            raise ToolError("Chapters are already being transcribed. Call wait first.")

        if chapter_ids is None:
            targets = [c for c in active_chapters(pipeline.chapters) if c.selected]
        else:
            targets = [resolve_chapter(pipeline.chapters, ref) for ref in chapter_ids]
        if not targets:
            raise ToolError("No chapters to transcribe")

        await app_state.enqueue_transcription([c.id for c in targets], is_batch=True)
        await settle(app_state, ctx, timeout_seconds)
        data = snapshot(app_state)
        if not data.get("busy"):
            data["transcribed"] = chapter_views(
                pipeline.chapters,
                pipeline.book_duration,
                "all",
                only_ids={c.id for c in targets},
                from_transcripts=titles_from_transcripts(pipeline),
            )
        return result(data)

    @server.tool(annotations=EDITS)
    @tool_errors
    async def scan_for_cues(
        chapter_id: Annotated[str, Field(description="Scan from this chapter's start to the next chapter's")],
        ctx: Context,
        mode: Annotated[
            Literal["normal", "vad"],
            Field(description="vad finds pauses under music or sound effects (dramatized books)"),
        ] = "normal",
        timeout_seconds: Timeout = DEFAULT_WAIT_SECONDS,
    ) -> CallToolResult:
        """Look for silences the first pass didn't scan (realignment only scans near the expected boundaries)
        in the span of one chapter, from its start to the next chapter's. To find a better start for chapter X,
        scan X and the chapter before it. Then check get_nearby_cues."""
        app_state = get_app_state()
        need_step(app_state, [Step.CHAPTER_EDITING], "scan for cues")
        pipeline = need_pipeline(app_state)
        if not pipeline.audio_file_path:
            raise ToolError("No audio file is available for scanning")
        if pipeline._partial_scan_task and not pipeline._partial_scan_task.done():
            raise ToolError("A scan is already running. Call wait first.")
        chapter = resolve_chapter(pipeline.chapters, chapter_id)
        before = len(pipeline.detected_cues)
        await pipeline.run_partial_scan(chapter.id, mode)
        await settle(app_state, ctx, timeout_seconds)
        data = snapshot(app_state)
        if not data.get("busy"):
            data["new_cues"] = len(pipeline.detected_cues) - before
        return result(data)

    @server.tool(annotations=EDITS)
    @tool_errors
    async def realign_unpinned() -> CallToolResult:
        """Re-run realignment around the pinned chapters and the chapters you added: every other realigned
        chapter is placed again, using the pins as ground truth (one undo step). After fixing a wrong chapter by
        moving it (which pins it), this often fixes the chapters after it too."""
        app_state = get_app_state()
        need_step(app_state, [Step.CHAPTER_EDITING], "re-run realignment")
        pipeline = need_pipeline(app_state)
        outcome = pipeline.rerun_realignment()
        await app_state.broadcast_chapter_update()
        await app_state.broadcast_history_update()
        return result({"realigned": outcome.realigned, "moved": outcome.moved, "next": "Check with list_chapters."})

    async def _history(action: str, steps: int) -> CallToolResult:
        app_state = get_app_state()
        need_step(app_state, [Step.CHAPTER_EDITING], action)
        pipeline = need_pipeline(app_state)
        can = pipeline.can_undo if action == "undo" else pipeline.can_redo
        step_fn = pipeline.undo if action == "undo" else pipeline.redo
        done = 0
        while done < steps and can():
            step_fn()
            done += 1
        if not done:
            raise ToolError(f"Nothing to {action}")
        await app_state.broadcast_chapter_update()
        await app_state.broadcast_history_update()
        return result({action: done, "can_undo": pipeline.can_undo(), "can_redo": pipeline.can_redo()})

    @server.tool(annotations=EDITS)
    @tool_errors
    async def undo(steps: Annotated[int, Field(ge=1, le=50)] = 1) -> CallToolResult:
        """Undo the last edit (an edit_chapters call, a realignment re-run, a transcription batch, or an edit the
        user made in the web UI; they share one history)."""
        return await _history("undo", steps)

    @server.tool(annotations=EDITS)
    @tool_errors
    async def redo(steps: Annotated[int, Field(ge=1, le=50)] = 1) -> CallToolResult:
        """Redo an undone edit."""
        return await _history("redo", steps)

    # -----------------------------------------------------------------------
    # Submitting
    # -----------------------------------------------------------------------

    @server.tool(annotations=READ_ONLY)
    @tool_errors
    async def preview_submission(
        full: Annotated[
            bool,
            Field(
                description=f"List every change (not just the first {MAX_LISTED_CHANGES}) and the whole chapter list "
                "as it would be written"
            ),
        ] = False,
    ) -> CallToolResult:
        """What submit_to_audiobookshelf would write, compared with the chapters Audiobookshelf has now, plus
        warnings (chapters past the end of the audio, untitled or unexpectedly short chapters, excluded
        chapters). Show this to the user before submitting."""
        app_state = get_app_state()
        need_step(app_state, [Step.CHAPTER_EDITING, Step.REVIEWING], "preview the submission")
        pipeline = need_pipeline(app_state)
        ordered = active_chapters(pipeline.chapters)
        final = [c for c in ordered if c.selected]
        if not final:
            raise ToolError("No chapters are included, so there's nothing to submit")

        writes = [(0.0 if i == 0 else c.timestamp, c.title) for i, c in enumerate(final)]
        warnings = session_warnings(pipeline)
        if final[0].timestamp > 0:
            warnings.append(f"The first chapter starts at {fmt_time(final[0].timestamp)}; it's written as 0:00:00")
        untitled = [i + 1 for i, c in enumerate(final) if not c.title.strip()]
        if untitled:
            warnings.append(f"Untitled chapters: {untitled}")
        expected_short = []
        for i, (t, title) in enumerate(writes):
            end = min(writes[i + 1][0] if i + 1 < len(writes) else pipeline.book_duration, pipeline.book_duration)
            if t >= end or end - t >= SHORT_CHAPTER_SECONDS or EXPECTED_SHORT_TITLE_RE.search(title):
                continue
            if _short_in_a_reference(pipeline, final[i]):
                expected_short.append(i + 1)
            else:
                warnings.append(f"Chapter {i + 1} ({quote(title)}) is only {end - t:.1f} s long")
        if expected_short:
            warnings.append(
                f"{len(expected_short)} chapters are under {SHORT_CHAPTER_SECONDS:.0f} s, as in a reference "
                f"(likely headings, no action needed): {expected_short}"
            )
        excluded = [c for c in ordered if not c.selected]
        if excluded:
            warnings.append(
                f"{len(excluded)} excluded chapters won't be written: "
                + ", ".join(f"{fmt_time(c.timestamp)} {quote(c.title)}" for c in excluded[:10])
            )

        diff, added = _diff(writes, _current_abs_chapters(pipeline), None if full else MAX_LISTED_CHANGES)
        new_chapters = [
            {"n": i + 1, "time": fmt_time(t), "title": title} for i, (t, title) in enumerate(writes) if i in added
        ]
        return result(
            {
                "book": pipeline.book.media.metadata.title if pipeline.book else None,
                "will_write": len(writes),
                "audiobookshelf_has": len(_current_abs_chapters(pipeline)),
                **diff,
                "warnings": warnings or None,
                # The whole list only on request: it's long for big books, and the counts, changes and
                # new chapters below say what changes
                "chapters": [
                    {"n": i + 1, "time": fmt_time(t), "title": title, "new": True if i in added else None}
                    for i, (t, title) in enumerate(writes)
                ]
                if full
                else None,
                "new_chapters": None if full else new_chapters[:MAX_LISTED_CHANGES] or None,
                "agents_can_submit": get_app_config().mcp.allow_submit,
            }
        )

    @server.tool(annotations=SUBMIT)
    @tool_errors
    async def submit_to_audiobookshelf(
        confirm: Annotated[
            bool, Field(description="Must be true: confirms the user agreed to replace the book's chapters")
        ] = False,
    ) -> CallToolResult:
        """Write the included chapters to Audiobookshelf, replacing the book's current chapters, and finish the
        session. Only call this after showing the user preview_submission and getting their go-ahead."""
        app_state = get_app_state()
        need_step(app_state, [Step.CHAPTER_EDITING, Step.REVIEWING], "submit")
        pipeline = need_pipeline(app_state)

        if not get_app_config().mcp.allow_submit:
            if pipeline.step == Step.CHAPTER_EDITING:
                pipeline.step = Step.REVIEWING
                await app_state.broadcast_step_change(Step.REVIEWING)
            raise ToolError(
                "The user has turned off submitting for agents (Settings → Agent Access). Achew's web UI is now "
                "showing the Review screen: ask the user to check it and click Submit there."
            )
        if not confirm:
            raise ToolError(
                "Show the user preview_submission and ask before replacing the book's chapters, then call again "
                "with confirm=true."
            )
        included = [c for c in active_chapters(pipeline.chapters) if c.selected]
        if not included:
            raise ToolError("No chapters are included, so there's nothing to submit")
        beyond = [c for c in included if c.timestamp >= pipeline.book_duration - BEYOND_AUDIO_MARGIN_SECONDS]
        if beyond:
            raise ToolError(
                f"{len(beyond)} included chapters start at or after the end of the audio "
                f"({', '.join(short_id(c) for c in beyond)}). Delete them first; see preview_submission."
            )
        count = len(included)

        await submit_to_abs(app_state, pipeline)
        data = snapshot(app_state)
        data["written"] = count
        return result(data)
