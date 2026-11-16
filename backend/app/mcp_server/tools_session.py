"""MCP tools for the session lifecycle and workflows: opening a book, choosing and running a
workflow, picking cues, transcription setup, references, and navigating between steps."""

import asyncio
import os
import shutil
import tempfile
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ToolAnnotations
from pydantic import Field

from app.api.routes.references import parse_reference_file
from app.app import get_app_state
from app.core.config import is_abs_configured
from app.models.enums import DetectionMode, RestartStep, Step
from app.models.references import ChapterReference, TitleReference
from app.services.asr_service_options import get_preferred_service
from app.services.session_actions import (
    audnexus_candidates,
    cancel_current_step,
    fetch_and_announce,
    fetch_audnexus_reference,
    validate_initial_selection,
    validate_preassigned_titles,
)

from .runtime import (
    DEFAULT_WAIT_SECONDS,
    EDITS,
    MAX_WAIT_SECONDS,
    READ_ONLY,
    TimeArg,
    coverage,
    cue_view,
    fmt_duration,
    fmt_time,
    in_window,
    jobs,
    need_pipeline,
    need_step,
    parse_time,
    result,
    run_and_settle,
    settle,
    snapshot,
    tool_errors,
)

Timeout = Annotated[
    float,
    Field(ge=0, le=MAX_WAIT_SECONDS, description="Seconds to wait for the work to finish before returning"),
]

DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
REMOTE_EDITS = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)

# Reference titles shown in summaries, enough to judge their quality without fetching the whole list
SAMPLE_TITLES = 5

# A requested cue timestamp this close to a detected cue snaps to it
CUE_SNAP_SECONDS = 1.0

# Cue counts the gap table reports thresholds for, besides the references' chapter counts
GAP_TABLE_COUNTS = [5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 125, 150, 200, 300]

# Gap lengths (seconds) the cumulative cue count is reported at
GAP_POINTS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0]

# Natural breaks: the largest ratios between consecutive gaps (sorted longest first), searched
# among the longest NATURAL_BREAK_WINDOW cues and ignoring gaps shorter than NATURAL_BREAK_MIN_GAP.
# Only drops of at least NATURAL_BREAK_MIN_RATIO are reported: in books without a clean
# separation (full-cast productions, scored transitions) every ratio sits near 1, and listing
# the largest of them would point the agent at noise.
NATURAL_BREAK_WINDOW = 300
NATURAL_BREAK_MIN_GAP = 0.5
NATURAL_BREAK_MIN_RATIO = 1.5
NATURAL_BREAKS = 3

REFERENCE_FORMATS = {"csv": ".csv", "cue": ".cue", "json": ".json", "txt": ".txt"}


def _require_transcription() -> None:
    if get_preferred_service() is None:
        raise ToolError(
            "No transcription service is set up. The user can choose one in Achew's web UI under "
            "Settings → Transcription Settings."
        )


def _reference_summary(ref: Union[ChapterReference, TitleReference], book_duration: float) -> Dict[str, Any]:
    if isinstance(ref, ChapterReference):
        return {
            "id": ref.id,
            "kind": "chapters",
            "type": ref.type.value,
            "name": ref.name,
            "also_known_as": ref.merged_names or None,
            "chapters": len(ref.chapters),
            "length": fmt_duration(ref.duration) if ref.duration else None,
            # Positive: the reference is longer than this book's audio
            "duration_difference": round(ref.duration - book_duration, 1) if ref.duration else None,
            "sample_titles": [c.title for c in ref.chapters[:SAMPLE_TITLES]],
        }
    return {
        "id": ref.id,
        "kind": "titles",
        "type": ref.type.value,
        "name": ref.name,
        "titles": len(ref.titles),
        "sample_titles": ref.titles[:SAMPLE_TITLES],
    }


def _references(pipeline) -> List[Dict[str, Any]]:
    duration = pipeline.book.duration if pipeline.book else 0.0
    return [_reference_summary(r, duration) for r in [*pipeline.chapter_refs, *pipeline.title_refs]]


def _chapter_ref(pipeline, ref_id: Optional[str]) -> ChapterReference:
    if not ref_id:
        raise ToolError("This workflow needs reference_id, a chapter reference from get_references")
    ref = next((r for r in pipeline.chapter_refs if r.id == ref_id), None)
    if ref is None:
        if any(r.id == ref_id for r in pipeline.title_refs):
            raise ToolError(f"{ref_id} is a title reference (titles only, no timestamps); pick a chapter reference")
        raise ToolError(f"No chapter reference with id {ref_id!r}; see get_references")
    return ref


def _gap_thresholds(gaps_desc: List[float], counts: List[int]) -> List[Dict[str, Any]]:
    """For each chapter count, the min_gap_seconds that selects about that many chapters."""
    rows = []
    for chapters in sorted(set(counts)):
        cues_needed = chapters - 1
        if cues_needed < 1 or cues_needed > len(gaps_desc):
            continue
        rows.append({"chapters": chapters, "min_gap_seconds": round(gaps_desc[cues_needed - 1], 2)})
    return rows


def _cues_at_least(gaps_desc: List[float]) -> List[Dict[str, Any]]:
    """How many cues have at least each of GAP_POINTS seconds of silence (and the chapters that makes)."""
    rows = []
    for gap in GAP_POINTS:
        count = sum(1 for g in gaps_desc if g >= gap)
        if count:
            rows.append({"gap": gap, "cues": count, "chapters": count + 1})
    return rows


def _natural_breaks(gaps_desc: List[float]) -> List[Dict[str, Any]]:
    """Places where the sorted gaps drop sharply, which often separate real chapter breaks
    from ordinary pauses."""
    window = [g for g in gaps_desc[:NATURAL_BREAK_WINDOW] if g >= NATURAL_BREAK_MIN_GAP]
    ratios = [(window[i] / window[i + 1], i) for i in range(len(window) - 1) if window[i + 1] > 0]
    breaks = []
    for ratio, i in sorted(ratios, reverse=True)[:NATURAL_BREAKS]:
        if ratio < NATURAL_BREAK_MIN_RATIO:
            break
        breaks.append(
            {
                "chapters": i + 2,
                "min_gap_seconds": round(window[i], 2),
                "next_gap_seconds": round(window[i + 1], 2),
                "drop_ratio": round(ratio, 2),
            }
        )
    return sorted(breaks, key=lambda b: b["chapters"])


def register(server: MCPServer) -> None:
    # -----------------------------------------------------------------------
    # Session lifecycle
    # -----------------------------------------------------------------------

    @server.tool(annotations=REMOTE_EDITS)
    @tool_errors
    async def open_book(
        item_id: Annotated[str, Field(description="Audiobookshelf item id, from search_books")],
        ctx: Context,
        timeout_seconds: Timeout = DEFAULT_WAIT_SECONDS,
    ) -> CallToolResult:
        """Open an Audiobookshelf book in Achew. Downloads its audio and gathers its chapter references
        (current Audiobookshelf chapters, chapters embedded in the files, Audnexus). Only one book can be open at
        a time, and it's shared with the web UI. Returns the references once the book is ready for
        start_workflow; for long downloads it returns `busy: true` and you call wait."""
        app_state = get_app_state()
        if not is_abs_configured():
            raise ToolError("Audiobookshelf isn't set up yet. The user needs to finish setup in Achew's web UI.")

        pipeline = app_state.pipeline
        if pipeline is not None:
            if pipeline.item_id == item_id:
                data = snapshot(app_state)
                data["already_open"] = True
                if pipeline.book:
                    data["references"] = _references(pipeline)
                return result(data)
            title = pipeline.book.media.metadata.title if pipeline.book else pipeline.item_id
            raise ToolError(
                f"'{title}' is already open (step {pipeline.step.value}), possibly by the user in the web UI. "
                "Finish or submit it first, or call close_session if the user agrees to discard it."
            )

        if jobs.running:
            raise ToolError(f"Still working on '{jobs.label}'. Call wait until it finishes.")
        pipeline = app_state.create_pipeline(item_id)
        data = await run_and_settle(
            "opening the book", lambda: fetch_and_announce(app_state, pipeline, item_id), ctx, timeout_seconds
        )
        if app_state.pipeline is pipeline and pipeline.step == Step.SELECT_WORKFLOW:
            data["references"] = _references(pipeline)
        return result(data)

    @server.tool(annotations=READ_ONLY)
    @tool_errors
    async def wait(ctx: Context, timeout_seconds: Timeout = DEFAULT_WAIT_SECONDS) -> CallToolResult:
        """Wait for running work (download, detection, transcription, realignment...) to finish, up to
        timeout_seconds, then return the session state. Call again while it says `busy: true`."""
        app_state = get_app_state()
        await settle(app_state, ctx, timeout_seconds)
        data = snapshot(app_state)
        pipeline = app_state.pipeline
        if pipeline is not None and pipeline.step == Step.SELECT_WORKFLOW and not data.get("busy"):
            data["references"] = _references(pipeline)
        return result(data)

    @server.tool(annotations=EDITS)
    @tool_errors
    async def cancel_processing() -> CallToolResult:
        """Stop the running step (detection, transcription, verification, a scan...) and go back to the last
        step that waits for input. Cancelling a download closes the book."""
        app_state = get_app_state()
        outcome = await cancel_current_step(app_state)
        await settle(app_state, None, 5)
        data = snapshot(app_state)
        data["cancelled"] = outcome["message"]
        return result(data)

    @server.tool(annotations=DESTRUCTIVE)
    @tool_errors
    async def go_back(
        to_step: Annotated[
            Literal["select_workflow", "initial_chapter_selection", "configure_asr", "chapter_editing"],
            Field(description="One of the session's go_back_options"),
        ],
    ) -> CallToolResult:
        """Return to an earlier step, like the web UI's back menu. Going back past chapter_editing discards the
        chapter edits, and back to select_workflow discards detection results too."""
        app_state = get_app_state()
        pipeline = need_pipeline(app_state)
        options = [getattr(o, "value", o) for o in pipeline.get_restart_options()]
        if to_step not in options:
            raise ToolError(f"Can't go back to {to_step} from {pipeline.step.value}. Options: {options or 'none'}")
        await pipeline.restart_at_step(RestartStep(to_step))
        await asyncio.sleep(0)
        return result(snapshot(app_state))

    @server.tool(annotations=DESTRUCTIVE)
    @tool_errors
    async def close_session() -> CallToolResult:
        """Close the open book and discard its session, including any chapter edits that weren't submitted. The
        web UI returns to the book search. Ask the user first if they may have been working on it."""
        app_state = get_app_state()
        pipeline = need_pipeline(app_state)
        await pipeline.restart_at_step(RestartStep.IDLE)
        await asyncio.sleep(0)
        return result(snapshot(app_state))

    # -----------------------------------------------------------------------
    # References
    # -----------------------------------------------------------------------

    @server.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_references(
        reference_id: Annotated[
            Optional[str], Field(description="A reference to list in full; omit for a summary of all")
        ] = None,
    ) -> CallToolResult:
        """Chapter references (timestamps + titles, e.g. the current Audiobookshelf chapters or Audnexus) and
        title references (titles only, e.g. an ebook's table of contents) for the open book. With reference_id,
        returns every chapter or title in it."""
        app_state = get_app_state()
        pipeline = need_pipeline(app_state)
        if not reference_id:
            return result({"references": _references(pipeline)})

        duration = pipeline.book.duration if pipeline.book else 0.0
        chapter_ref = next((r for r in pipeline.chapter_refs if r.id == reference_id), None)
        if chapter_ref is not None:
            data = _reference_summary(chapter_ref, duration)
            data.pop("sample_titles")
            data["chapter_list"] = [
                {"n": i + 1, "start": round(c.timestamp, 2), "time": fmt_time(c.timestamp), "title": c.title}
                for i, c in enumerate(chapter_ref.chapters)
            ]
            return result(data)
        title_ref = next((r for r in pipeline.title_refs if r.id == reference_id), None)
        if title_ref is not None:
            data = _reference_summary(title_ref, duration)
            data.pop("sample_titles")
            data["title_list"] = title_ref.titles
            return result(data)
        raise ToolError(f"No reference with id {reference_id!r}")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
    @tool_errors
    async def find_audnexus_chapters(
        title: Annotated[Optional[str], Field(description="Defaults to the open book's title")] = None,
        author: Annotated[Optional[str], Field(description="Defaults to the open book's author")] = None,
        provider: Annotated[
            str, Field(description="Audible marketplace, e.g. audible, audible.uk, audible.de")
        ] = "audible",
    ) -> CallToolResult:
        """Search Audible for editions of the book that have Audnexus chapter data. Compare each candidate's
        length with the open book's (`duration_difference` near 0 means the same edition), then add the best one
        with add_audnexus_reference."""
        app_state = get_app_state()
        pipeline = app_state.pipeline
        book = pipeline.book if pipeline else None
        if book is None and not title:
            raise ToolError("Open a book first, or pass a title")
        metadata = book.media.metadata if book else None
        candidates = await audnexus_candidates(
            provider=provider,
            title=title or (metadata.title if metadata else ""),
            author=author or (metadata.authorName if metadata and metadata.authorName else ""),
            book_id=book.id if book else "",
        )
        rows = []
        for found, chapters in candidates:
            runtime = chapters.runtimeLengthMs / 1000
            rows.append(
                {
                    "asin": found.asin,
                    "title": found.title,
                    "author": found.author,
                    "narrators": found.narrators or None,
                    "chapters": len(chapters.chapters),
                    "length": fmt_duration(runtime),
                    "duration_difference": round(runtime - book.duration, 1) if book else None,
                    "accurate": chapters.isAccurate,
                    "sample_titles": [c.title for c in chapters.chapters[:SAMPLE_TITLES]],
                }
            )
        return result({"candidates": rows})

    @server.tool(annotations=REMOTE_EDITS)
    @tool_errors
    async def add_audnexus_reference(
        asin: Annotated[str, Field(description="ASIN from find_audnexus_chapters")],
        provider: Annotated[str, Field(description="Audible marketplace the ASIN belongs to")] = "audible",
    ) -> CallToolResult:
        """Add an edition's Audnexus chapters to the open book as a chapter reference."""
        app_state = get_app_state()
        pipeline = need_pipeline(app_state)
        ref = await fetch_audnexus_reference(asin.strip(), provider)
        pipeline.chapter_refs.append(ref)
        await app_state.broadcast_references_update()
        return result({"added": _reference_summary(ref, pipeline.book.duration if pipeline.book else 0.0)})

    @server.tool(annotations=EDITS)
    @tool_errors
    async def add_reference_from_text(
        name: Annotated[str, Field(description="A name for the reference, shown in the web UI")],
        format: Annotated[
            Literal["csv", "cue", "json", "txt"],
            Field(
                description="csv/cue/json: a chapter reference with timestamps (the formats Achew exports). "
                "txt: a title reference, one title per line."
            ),
        ],
        content: Annotated[str, Field(description="The file's contents")],
    ) -> CallToolResult:
        """Add a reference from text, the same as uploading a file in the web UI. Use txt for a list of titles
        (e.g. from a table of contents) to apply to chapters whose timing is already right."""
        app_state = get_app_state()
        pipeline = need_pipeline(app_state)
        ext = REFERENCE_FORMATS[format]
        filename = name.strip() or "Reference"
        if not filename.lower().endswith(ext):
            filename += ext
        temp_dir = tempfile.mkdtemp(prefix="achew_mcp_ref_")
        try:
            path = os.path.join(temp_dir, f"reference{ext}")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            ref = parse_reference_file(pipeline, path, filename, ext)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        await app_state.broadcast_references_update()
        return result({"added": _reference_summary(ref, pipeline.book.duration if pipeline.book else 0.0)})

    # -----------------------------------------------------------------------
    # Workflows
    # -----------------------------------------------------------------------

    @server.tool(annotations=EDITS)
    @tool_errors
    async def start_workflow(
        workflow: Annotated[
            Literal["realign", "regenerate", "quick_edit", "smart_detect"],
            Field(
                description="realign: move a reference's chapters onto the audio's real boundaries (keeps its "
                "titles). regenerate: keep a reference's timestamps, re-title chapters from transcription. "
                "quick_edit: load a reference into the editor as-is. smart_detect: detect chapters from silences "
                "in the audio, then title them by transcription."
            ),
        ],
        ctx: Context,
        reference_id: Annotated[
            Optional[str], Field(description="Chapter reference to start from (all workflows but smart_detect)")
        ] = None,
        detection_mode: Annotated[
            Literal["auto", "standard", "dramatized"],
            Field(
                description="realign/smart_detect: 'dramatized' detects pauses under music and sound effects "
                "(full-cast productions); 'auto' checks the book and picks"
            ),
        ] = "auto",
        thorough: Annotated[
            bool, Field(description="realign: scan far more audio around each chapter (slower; for big shifts)")
        ] = False,
        transcribe: Annotated[
            bool,
            Field(description="realign: verify chapter starts by transcription (needs a transcription service)"),
        ] = False,
        timeout_seconds: Timeout = DEFAULT_WAIT_SECONDS,
    ) -> CallToolResult:
        """Run a workflow on the open book (at select_workflow). Returns at the next step that needs input, or
        with `busy: true` (call wait). realign ends in chapter_editing; regenerate in configure_asr; smart_detect
        in initial_chapter_selection; with transcribe=true, realign first stops at configure_asr."""
        app_state = get_app_state()
        need_step(app_state, [Step.SELECT_WORKFLOW], "start a workflow")
        pipeline = need_pipeline(app_state)
        if workflow != "smart_detect":
            _chapter_ref(pipeline, reference_id)
        if transcribe and workflow == "realign":
            _require_transcription()

        mode = DetectionMode(detection_mode)
        data = await run_and_settle(
            f"{workflow} workflow",
            lambda: pipeline.start_workflow(
                workflow, reference_id, mode, thorough, transcribe and workflow == "realign"
            ),
            ctx,
            timeout_seconds,
        )
        return result(data)

    @server.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_detected_cues(
        min_gap_seconds: Annotated[
            Optional[float], Field(ge=0, description="Only list cues whose silence is at least this long")
        ] = None,
        from_time: Annotated[TimeArg, Field(description="Only list cues from this time (seconds or h:mm:ss)")] = None,
        to_time: Annotated[TimeArg, Field(description="Only list cues up to this time (seconds or h:mm:ss)")] = None,
        max_cues: Annotated[int, Field(ge=1, le=1000, description="List at most this many (the longest gaps)")] = 150,
    ) -> CallToolResult:
        """The silences detection found (cues): at initial_chapter_selection, for choosing which become chapters
        with select_cues; in the editor, to look for boundaries in a stretch of the book (from_time/to_time).
        Longer gaps are likelier chapter breaks, but long pauses happen mid-chapter too, and a real break can be
        short. Check doubtful cues with transcribe_audio.

        Also returns, book-wide: `cues_at_least` (how many cues have at least each gap length), `thresholds`
        (the min_gap_seconds that gives likely chapter counts, including each reference's), and any
        `natural_breaks` where gap lengths drop sharply (often absent in full-cast or scored books).
        `total_matching` counts the cues your filters match, before max_cues. `scanned` says how much of the
        requested stretch has been scanned for silences at all: after a realignment only the audio near the
        reference's starts has, so no cues elsewhere means "not looked at", not "no silences".

        A cue marks where speech resumes after a silence: its time is 1/3 s before the silence ends, and the
        silence (`gap` seconds long) began at `silence_from`."""
        app_state = get_app_state()
        need_step(
            app_state, [Step.INITIAL_CHAPTER_SELECTION, Step.CHAPTER_EDITING, Step.REVIEWING], "list detected cues"
        )
        pipeline = need_pipeline(app_state)
        cues = sorted(pipeline.detected_cues, key=lambda c: c.timestamp)
        gaps_desc = sorted((c.gap for c in cues), reverse=True)

        ref_counts = {r.name: len(r.chapters) for r in pipeline.chapter_refs if len(r.chapters) > 1}
        listed = [c for c in in_window(cues, from_time, to_time) if min_gap_seconds is None or c.gap >= min_gap_seconds]
        matching = len(listed)
        if len(listed) > max_cues:
            keep = {id(c) for c in sorted(listed, key=lambda c: c.gap, reverse=True)[:max_cues]}
            listed = [c for c in listed if id(c) in keep]

        return result(
            {
                "book_length": fmt_duration(pipeline.book_duration),
                "total_cues": len(cues),
                "reference_chapter_counts": ref_counts or None,
                "cues_at_least": _cues_at_least(gaps_desc),
                "thresholds": _gap_thresholds(gaps_desc, GAP_TABLE_COUNTS + list(ref_counts.values())),
                "natural_breaks": _natural_breaks(gaps_desc) or None,
                "scanned": coverage(
                    pipeline,
                    parse_time(from_time) if from_time is not None else 0.0,
                    parse_time(to_time) if to_time is not None else pipeline.book_duration,
                ),
                "total_matching": matching,
                "cues": [cue_view(c) for c in listed],
                "listed": f"{len(listed)} of {matching} (longest gaps)" if len(listed) < matching else None,
            }
        )

    @server.tool(annotations=EDITS)
    @tool_errors
    async def select_cues(
        ctx: Context,
        min_gap_seconds: Annotated[
            Optional[float], Field(ge=0, description="Make every cue with at least this much silence a chapter")
        ] = None,
        timestamps: Annotated[
            Optional[List[Union[float, str]]],
            Field(
                description="Specific cue times (seconds or h:mm:ss) to make chapters, alone or on top of "
                "min_gap_seconds. Times within 1 s of a detected cue snap to it."
            ),
        ] = None,
        exclude_timestamps: Annotated[
            Optional[List[Union[float, str]]],
            Field(
                description="Cue times to leave out of what min_gap_seconds selects (e.g. mid-chapter pauses). "
                "Matched to the selected cue within 1 s"
            ),
        ] = None,
        include_unaligned_from: Annotated[
            Optional[List[str]],
            Field(description="Chapter reference ids whose chapters with no nearby cue should be added anyway"),
        ] = None,
        timeout_seconds: Timeout = DEFAULT_WAIT_SECONDS,
    ) -> CallToolResult:
        """Choose which detected cues become chapters (at initial_chapter_selection): every cue with at least
        min_gap_seconds of silence, plus any timestamps, minus any exclude_timestamps. A chapter always starts
        at 0:00. Moves on to configure_asr."""
        app_state = get_app_state()
        need_step(app_state, [Step.INITIAL_CHAPTER_SELECTION], "select cues")
        pipeline = need_pipeline(app_state)
        if min_gap_seconds is None and not timestamps:
            raise ToolError("Pass min_gap_seconds, timestamps, or both (exclude_timestamps only removes from those)")

        cues = pipeline.detected_cues
        chosen = {0.0}
        if min_gap_seconds is not None:
            chosen.update(c.timestamp for c in cues if c.gap >= min_gap_seconds)
        snapped = 0
        for value in timestamps or []:
            t = parse_time(value)
            if not 0 <= t < pipeline.book_duration:
                raise ToolError(f"{value} is outside the book (0 to {fmt_duration(pipeline.book_duration)})")
            nearest = min(cues, key=lambda c: abs(c.timestamp - t), default=None)
            if nearest is not None and abs(nearest.timestamp - t) <= CUE_SNAP_SECONDS:
                snapped += nearest.timestamp != t
                t = nearest.timestamp
            chosen.add(t)

        unmatched_excludes = []
        excluded = 0
        for value in exclude_timestamps or []:
            t = parse_time(value)
            nearest = min((c for c in chosen if c > 0), key=lambda c: abs(c - t), default=None)
            if nearest is None or abs(nearest - t) > CUE_SNAP_SECONDS:
                unmatched_excludes.append(value)
                continue
            chosen.discard(nearest)
            excluded += 1

        selection = sorted(chosen)
        include = include_unaligned_from or []
        validate_initial_selection(pipeline, selection, include)
        data = await run_and_settle(
            "selecting cues", lambda: pipeline.select_initial_chapters(selection, include), ctx, timeout_seconds
        )
        data["chapters_selected"] = len(pipeline.cues) if pipeline.cues else len(selection)
        if snapped:
            data["snapped_to_cues"] = snapped
        if exclude_timestamps:
            data["excluded"] = excluded
            data["excludes_not_selected"] = unmatched_excludes or None
        return result(data)

    @server.tool(annotations=EDITS)
    @tool_errors
    async def configure_transcription(
        action: Annotated[
            Literal["transcribe", "skip"],
            Field(
                description="transcribe: title each chapter from what's said at its start. skip: no transcription "
                "(chapters get the titles below, or stay untitled)."
            ),
        ],
        ctx: Context,
        titles: Annotated[
            Optional[List[Optional[str]]],
            Field(
                description="Titles for the chapters in the order of the session's chapter_starts (first = the "
                "chapter at 0:00). A title skips transcription for that chapter; null leaves it to transcription."
            ),
        ] = None,
        timeout_seconds: Timeout = DEFAULT_WAIT_SECONDS,
    ) -> CallToolResult:
        """Continue from configure_asr. For a realignment waiting on transcription settings (realign_pending),
        'transcribe' runs the verified realignment and 'skip' runs a plain one. Otherwise this creates the
        chapters, transcribing their starts with the transcription service the user set up in the web UI."""
        app_state = get_app_state()
        need_step(app_state, [Step.CONFIGURE_ASR], "configure transcription")
        pipeline = need_pipeline(app_state)
        if action == "transcribe":
            _require_transcription()

        if pipeline.pending_realign is not None:
            if titles:
                raise ToolError("titles don't apply to a realignment")
            data = await run_and_settle(
                "realignment",
                lambda: pipeline.resume_pending_realign(transcribe=action == "transcribe"),
                ctx,
                timeout_seconds,
            )
            return result(data)

        pairs = [(i, t.strip()) for i, t in enumerate(titles or []) if t is not None and t.strip()]
        preassigned = validate_preassigned_titles(pipeline, pairs)
        if action == "transcribe":
            work = lambda: pipeline.proceed_with_transcription(preassigned_titles=preassigned)  # noqa: E731
        else:
            work = lambda: pipeline.skip_transcription(preassigned_titles=preassigned)  # noqa: E731
        data = await run_and_settle("creating chapters", work, ctx, timeout_seconds)
        return result(data)

    @server.tool(annotations=EDITS)
    @tool_errors
    async def finish_verification(ctx: Context, timeout_seconds: Timeout = DEFAULT_WAIT_SECONDS) -> CallToolResult:
        """Stop a transcription-verified realignment early, keeping the chapters confirmed so far."""
        app_state = get_app_state()
        pipeline = need_pipeline(app_state)
        pipeline.request_finish_verification()
        await settle(app_state, ctx, timeout_seconds)
        return result(snapshot(app_state))
