"""Plumbing shared by the MCP tools: results, errors, time parsing, the background job
runner behind every long-running tool, and the session snapshot those tools return.

Achew's workflows run for seconds to many minutes and report progress over the WebSocket,
which an agent can't listen to. Tools that start one run it as a job here and wait for the
session to settle at a step that needs input, up to a timeout. If the work outlasts it, the
tool returns with `busy: true`, and the agent calls `wait` until it settles. The job keeps
running in the background either way, so a tool call timing out on the client side never
cancels the work.
"""

import asyncio
import functools
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, TypeVar, Union

from fastapi import HTTPException
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from app.app import AppState, get_app_state
from app.core.constants import CHAPTER_START_PADDING, REALIGN_PADDING_EXPANDED
from app.models.chapter import ChapterData
from app.models.enums import Step
from app.services.realign_verification import STRONG_MATCH_SCORE
from app.services.title_matching import NUMBER_KEYWORDS, announces_chapter, match_title, normalize, title_profile

logger = logging.getLogger(__name__)

# How often `wait` re-checks the session, and the bounds on how long one call may block.
# Kept under the 60 s per-request timeout many MCP clients use by default.
POLL_INTERVAL_SECONDS = 0.5
DEFAULT_WAIT_SECONDS = 50
MAX_WAIT_SECONDS = 300

# An error banner this recent is reported in snapshots that aren't tied to a job
RECENT_ERROR_SECONDS = 300

# Chapter starts listed at configure_asr
MAX_LISTED_STARTS = 500

# A chapter starting this close to the end of the audio (or after it) has no audio of its own.
# Realigning to a reference from a longer copy of the book leaves its last chapters there.
BEYOND_AUDIO_MARGIN_SECONDS = 1.0

# A reference this much longer than the recording suggests the recording is missing audio
MISSING_AUDIO_SECONDS = 60.0

# Workflow summaries list the ids of up to MAX_GUESS_IDS unconfirmed guesses. When at least
# MOSTLY_GUESSES of a book's (at least MIN_REALIGNED) realigned chapters are guesses, results
# suggest a wider search or listening.
MAX_GUESS_IDS = 20
MOSTLY_GUESSES = 0.5
MIN_REALIGNED = 4

# A chapter this close to where one of the book's audio files starts counts as on that file's start
FILE_START_TOLERANCE_SECONDS = 1.0

# Unscanned stretches listed per coverage report
MAX_UNSCANNED_LISTED = 5

# Long headings: in a book with at least MIN_HEADINGS "Chapter N"-style chapters whose typical
# (median) length is under SHORT_HEADING_SECONDS, a heading at least LONG_HEADING_FACTOR times
# that (and at least LONG_HEADING_MIN_SECONDS) has probably swallowed its first section. The
# section start is looked for among the first SECTION_CANDIDATES pauses of SECTION_MIN_GAP
# seconds or more, starting HEADING_SPOKEN_SECONDS in (after the heading is read) and within
# SECTION_SEARCH_SECONDS of the start.
MIN_HEADINGS = 3
SHORT_HEADING_SECONDS = 60.0
LONG_HEADING_FACTOR = 5.0
LONG_HEADING_MIN_SECONDS = 120.0
HEADING_SPOKEN_SECONDS = 1.5
SECTION_SEARCH_SECONDS = 120.0
SECTION_MIN_GAP = 1.0
SECTION_CANDIDATES = 3

# Steps where the session waits for input. Every other step means work is running.
INTERACTIVE_STEPS = {
    Step.MIGRATION_FAILED,
    Step.WELCOME,
    Step.ABS_SETUP,
    Step.LLM_SETUP,
    Step.ASR_SETUP,
    Step.IDLE,
    Step.SELECT_WORKFLOW,
    Step.INITIAL_CHAPTER_SELECTION,
    Step.CONFIGURE_ASR,
    Step.CHAPTER_EDITING,
    Step.REVIEWING,
    Step.COMPLETED,
}
SETUP_STEPS = {Step.MIGRATION_FAILED, Step.WELCOME, Step.ABS_SETUP, Step.LLM_SETUP, Step.ASR_SETUP}

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
EDITS = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


# ---------------------------------------------------------------------------
# Tools revision
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def tools_revision() -> str:
    """A short hash of this package's code and guide.

    Clients load tool descriptions when they connect, and a stateless server can't tell them
    the tools changed, so after an update (or a dev reload) they keep the old descriptions. The
    connect-time instructions carry the revision they were sent with and get_status reports the
    current one; an agent that sees them differ knows to have the user reconnect.
    """
    digest = hashlib.sha1()
    package = Path(__file__).parent
    for path in sorted([*package.glob("*.py"), package / "guide.md"]):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:8]


# ---------------------------------------------------------------------------
# Results and errors
# ---------------------------------------------------------------------------


def _prune(value: Any) -> Any:
    """Drop None values from dicts (recursively) so results only carry what's set."""
    if isinstance(value, dict):
        return {k: _prune(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_prune(v) for v in value]
    return value


def result(data: Dict[str, Any]) -> CallToolResult:
    """A tool result as compact JSON, both as text (what the model reads) and structured."""
    clean = _prune(data)
    text = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=clean)


def tool_errors(fn: F) -> F:
    """Report anticipated failures to the agent as tool errors with their message.

    The SDK hides the text of unexpected exceptions, so the checks shared with the REST API
    (which raise `HTTPException`) and argument problems (`ValueError`) are re-raised as
    `ToolError`, whose message the model sees.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except ToolError:
            raise
        except HTTPException as e:
            raise ToolError(str(e.detail)) from e
        except ValueError as e:
            raise ToolError(str(e)) from e

    return wrapper  # type: ignore[return-value]


def need_pipeline(app_state: AppState):
    if not app_state.pipeline:
        raise ToolError("No book is open. Find one with search_books, then call open_book.")
    return app_state.pipeline


def need_step(app_state: AppState, allowed: List[Step], action: str) -> None:
    pipeline = need_pipeline(app_state)
    if pipeline.step in allowed:
        return
    reason = busy_reason(app_state)
    if reason:
        raise ToolError(f"Can't {action} while Achew is busy ({reason}). Call wait first.")
    names = " or ".join(s.value for s in allowed)
    raise ToolError(f"Can't {action} at step {pipeline.step.value}; this needs {names}. {next_hint(app_state)}")


def session_step(app_state: AppState) -> Step:
    """The open book's step. The web UI's own step can differ: it shows setup pages (the user
    opened Transcription Settings, say) over the session, which carries on underneath."""
    if app_state.pipeline is not None:
        return app_state.pipeline.step
    return app_state.step


# ---------------------------------------------------------------------------
# Times
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)\s*$")


def quote(text: Optional[str]) -> str:
    """Quote a title for a message. repr() would escape characters such as non-breaking spaces
    (common in Audnexus titles) as \\xa0, which the plain title elsewhere in a result doesn't show."""
    return f"\u201c{text or ''}\u201d"


def fmt_time(seconds: float) -> str:
    """h:mm:ss.s, the form chapter starts are shown in."""
    tenths = int(round(max(0.0, seconds) * 10))
    hours, rem = divmod(tenths, 36000)
    minutes, rem = divmod(rem, 600)
    return f"{hours}:{minutes:02d}:{rem // 10:02d}.{rem % 10}"


def fmt_duration(seconds: float) -> str:
    """A length as h:mm:ss (or m:ss under an hour)."""
    total = int(round(max(0.0, seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def parse_time(value: float | int | str) -> float:
    """Seconds from a number or an "h:mm:ss(.s)" / "mm:ss" string."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    match = _TIME_RE.match(text)
    if not match:
        raise ValueError(f"Can't read {value!r} as a time; use seconds or h:mm:ss")
    hours, minutes, secs = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + float(secs)


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------

# Chapter ids are UUIDs; tools show and accept the first SHORT_ID_LENGTH hex digits, and
# accept any unique prefix of at least MIN_ID_PREFIX.
SHORT_ID_LENGTH = 8
MIN_ID_PREFIX = 4


def short_id(chapter: ChapterData) -> str:
    return chapter.id.replace("-", "")[:SHORT_ID_LENGTH]


def resolve_chapter(chapters: List[ChapterData], ref: str, include_deleted: bool = False) -> ChapterData:
    """Find a chapter by its full id or a unique id prefix."""
    key = ref.strip().lower().replace("-", "")
    pool = [c for c in chapters if include_deleted or not c.deleted]
    exact = [c for c in pool if c.id.replace("-", "") == key]
    if exact:
        return exact[0]
    if len(key) < MIN_ID_PREFIX:
        raise ValueError(f"Chapter id {ref!r} is too short; use the ids list_chapters shows")
    matches = [c for c in pool if c.id.replace("-", "").startswith(key)]
    if not matches:
        raise ValueError(f"No chapter with id {ref!r}; call list_chapters for current ids")
    if len(matches) > 1:
        raise ValueError(f"Chapter id {ref!r} matches {len(matches)} chapters; use more characters")
    return matches[0]


def active_chapters(chapters: List[ChapterData]) -> List[ChapterData]:
    return sorted((c for c in chapters if not c.deleted), key=lambda c: c.timestamp)


TranscriptMode = Literal["differing", "all", "none"]


# A track number that titles taken from file names carry ("01 - Chapter 1", "001. Prologue",
# "Track 3 - Down the Rabbit Hole"). Only stripped when a separator follows, so "12 Angry Men"
# keeps its number.
TRACK_PREFIX_RE = re.compile(r"^\s*(?:track\s*)?\d+\s*[-\u2013\u2014.:)_]+\s*(?=\S)", re.IGNORECASE)

_SENTENCE_START_RE = re.compile(r"(?<=[.!?;:])\s+")


def strip_track_prefix(title: str) -> str:
    return TRACK_PREFIX_RE.sub("", title)


def transcript_matches_title(title: str, transcript: str) -> bool:
    """Whether a chapter's transcript announces its title ("Two." for "2", "Chapter One. It was..."
    for "Chapter 1"), using the matcher behind transcription-verified realignment. Track-number
    prefixes in the title are ignored, and the title may open any sentence of the transcript (it
    often follows a preamble: "Chapter 1 of Alice in Wonderland. This is a LibriVox recording...")."""
    title = strip_track_prefix(title)
    if not title.strip() or not transcript.strip():
        return False
    title_tokens = normalize(title)
    if title_tokens == normalize(transcript):
        return True
    profile = title_profile(title)
    sentences = _SENTENCE_START_RE.split(transcript.strip())
    numbers = [t for t in title_tokens if t.isdigit()]
    for i in range(len(sentences)):
        rest = " ".join(sentences[i:])
        # A numbered section ("Chapter 1.2") is announced by its own number alone ("Two.")
        if len(numbers) >= 2 and normalize(sentences[i])[:1] == numbers[-1:]:
            return True
        if profile.tokens:
            match = match_title(rest, profile)
            if match.score >= STRONG_MATCH_SCORE and not match.number_conflict:
                return True
    return False


def announced_heading(transcript: str) -> Optional[str]:
    """The first chapter heading a transcript announces at a sentence start ("Chapter 5" from
    "Chapter 5 of Oliver Twist. This LibriVox recording..."), however the rest reads."""
    for sentence in _SENTENCE_START_RE.split(transcript.strip()):
        if not announces_chapter(sentence):
            continue
        tokens = normalize(sentence)
        if tokens[0].isdigit():
            return tokens[0]
        number = next(t for t in tokens[1:3] if t.isdigit())
        return f"{tokens[0].capitalize()} {number}"
    return None


def chapter_view(
    chapter: ChapterData,
    number: int,
    next_start: Optional[float],
    book_duration: float,
    transcripts: TranscriptMode = "differing",
    suspect: Optional[str] = None,
    titles_from_transcripts: bool = True,
    file_starts: Optional[List[float]] = None,
) -> Dict[str, Any]:
    beyond = chapter.timestamp >= book_duration - BEYOND_AUDIO_MARGIN_SECONDS
    end = book_duration if next_start is None else min(next_start, book_duration)
    view: Dict[str, Any] = {
        "id": short_id(chapter),
        "n": number,
        "start": round(chapter.timestamp, 2),
        "time": fmt_time(chapter.timestamp),
        "length": fmt_duration(max(0.0, end - chapter.timestamp)),
        "title": chapter.title,
        "beyond_audio": True if beyond else None,
    }
    if transcripts != "none" and chapter.transcript:
        if titles_from_transcripts and chapter.title.strip() == chapter.transcript.strip():
            # Titled by transcription and not edited since, so comparing the two proves nothing. (A
            # reference title that happens to equal the transcript is a real match.)
            view["title_is_transcript"] = True
        else:
            matches = transcript_matches_title(chapter.title, chapter.transcript)
            view["transcript_matches"] = matches
            if transcripts == "all" or not matches:
                view["transcript"] = chapter.transcript
    view["suspect"] = suspect
    if file_starts and len(file_starts) > 1:
        view["on_file_start"] = any(abs(chapter.timestamp - f) <= FILE_START_TOLERANCE_SECONDS for f in file_starts)
    if not chapter.selected:
        view["excluded"] = True
    if chapter.realignment:
        r = chapter.realignment
        if r.pinned:
            # Confirmed (by the user, an agent, or transcription), so the aligner's confidence and
            # guess flag no longer say anything
            view["realign"] = {"pinned": True, "reference_start": round(r.original_timestamp, 2)}
        else:
            view["realign"] = {
                "confidence": round(r.confidence, 2),
                "guess": r.is_guess or None,
                "reference_start": round(r.original_timestamp, 2),
            }
    return view


def titles_from_transcripts(pipeline) -> bool:
    """Whether the workflow titled chapters by transcription (smart detect, regenerate) rather than
    from a reference (realign, quick edit)."""
    return not (pipeline.is_realignment or pipeline.is_quick_edit)


def chapter_views(
    chapters: List[ChapterData],
    book_duration: float,
    transcripts: TranscriptMode = "differing",
    only_ids: Optional[set] = None,
    cues: Optional[list] = None,
    from_transcripts: bool = True,
    file_starts: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """Views of the active chapters in order (numbered among all of them), optionally just some."""
    ordered = active_chapters(chapters)
    suspects = long_headings(ordered, book_duration, cues or [])
    views = []
    for i, chapter in enumerate(ordered):
        if only_ids is not None and chapter.id not in only_ids:
            continue
        next_start = ordered[i + 1].timestamp if i + 1 < len(ordered) else None
        views.append(
            chapter_view(
                chapter,
                i + 1,
                next_start,
                book_duration,
                transcripts,
                suspects.get(chapter.id),
                from_transcripts,
                file_starts,
            )
        )
    return views


def _is_heading(title: str) -> bool:
    """A structural heading title: "Chapter 3", "Part One: Operation Michael", "Book II"."""
    tokens = normalize(title)
    return len(tokens) >= 2 and tokens[0] in NUMBER_KEYWORDS and tokens[1].isdigit()


def long_headings(ordered: List[ChapterData], book_duration: float, cues) -> Dict[str, str]:
    """Heading chapters that run far longer than the book's other headings, by chapter id.

    In books chaptered by section ("Chapter 3" then "One", "Two"...), headings are short, and
    one that runs for minutes has usually swallowed its first section, whose start was missed.
    The message points at the first pauses after the spoken heading, the likeliest section starts.
    """
    lengths = {}
    for i, chapter in enumerate(ordered):
        if _is_heading(chapter.title):
            end = ordered[i + 1].timestamp if i + 1 < len(ordered) else book_duration
            lengths[chapter.id] = (chapter, min(end, book_duration) - chapter.timestamp)
    if len(lengths) < MIN_HEADINGS:
        return {}
    typical = sorted(length for _, length in lengths.values())[len(lengths) // 2]
    if typical >= SHORT_HEADING_SECONDS:
        return {}

    flagged = {}
    for chapter_id, (chapter, length) in lengths.items():
        if length < max(LONG_HEADING_MIN_SECONDS, LONG_HEADING_FACTOR * typical):
            continue
        message = (
            f"A heading that runs {fmt_duration(length)}, while this book's headings are typically "
            f"{fmt_duration(typical)}: its first section probably starts inside it, unmarked."
        )
        window_end = chapter.timestamp + min(length, SECTION_SEARCH_SECONDS)
        pauses = [
            c
            for c in cues
            if chapter.timestamp + HEADING_SPOKEN_SECONDS <= c.timestamp < window_end and c.gap >= SECTION_MIN_GAP
        ][:SECTION_CANDIDATES]
        if pauses:
            listed = ", ".join(f"{fmt_time(c.timestamp)} ({c.gap:.1f} s)" for c in pauses)
            message += f" First pauses after the heading: {listed}. Listen there with transcribe_audio."
        else:
            message += " No detected pauses there yet; scan_for_cues on this chapter finds them."
        flagged[chapter_id] = message
    return flagged


CUE_TIME_NOTE = (
    "A cue marks where speech resumes after a silence: its time is 1/3 s before the silence ends, and the "
    "silence (`gap` seconds long) began at `silence_from`. A chapter placed on a cue starts with the words after it."
)


def cue_view(cue, chapter_start: Optional[float] = None) -> Dict[str, Any]:
    silence_end = cue.timestamp + CHAPTER_START_PADDING
    view: Dict[str, Any] = {
        "start": round(cue.timestamp, 2),
        "time": fmt_time(cue.timestamp),
        "gap": round(cue.gap, 2),
        "silence_from": fmt_time(max(0.0, silence_end - cue.gap)),
    }
    if chapter_start is not None:
        view["offset"] = round(cue.timestamp - chapter_start, 2)
    return view


TimeArg = Optional[Union[float, str]]


def in_window(cues, from_time: TimeArg, to_time: TimeArg) -> list:
    """Cues whose time falls in [from_time, to_time] (either end open when not given)."""
    low = parse_time(from_time) if from_time is not None else float("-inf")
    high = parse_time(to_time) if to_time is not None else float("inf")
    if low > high:
        raise ValueError("from_time is after to_time")
    return [c for c in cues if low <= c.timestamp <= high]


def pauses_between(cues, start: float, end: float) -> List[Dict[str, Any]]:
    """Detected silences that overlap [start, end), as "from–to (length)"."""
    found = []
    for cue in cues:
        silence_end = cue.timestamp + CHAPTER_START_PADDING
        silence_start = silence_end - cue.gap
        if silence_start < end and silence_end > start:
            found.append(
                {
                    "from": fmt_time(max(0.0, silence_start)),
                    "to": fmt_time(silence_end),
                    "seconds": round(cue.gap, 1),
                }
            )
    return found


def scanned_regions(pipeline) -> List[tuple]:
    """Where Achew has looked for silences: full-book detection, partial scans, and the windows a
    realignment scanned around each reference chapter (rebuilt from the chapters' reference starts,
    since realignment doesn't record them)."""
    regions = list(pipeline.normal_scanned_regions) + list(pipeline.vad_scanned_regions)
    context = pipeline._realignment_context
    if context is not None:
        duration = pipeline.book_duration
        for chapter in pipeline.chapters:  # deleted ones too: their windows were scanned
            if chapter.realignment and chapter.realignment.original_timestamp < duration:
                start = chapter.realignment.original_timestamp
                regions.append((max(0.0, start - context.padding), min(duration, start + context.padding)))
    return pipeline._merge_regions(regions) if regions else []


def coverage(pipeline, start: float, end: float) -> Dict[str, Any]:
    """How much of [start, end] has been scanned for silences, and the stretches that haven't."""
    if end <= start:
        return {"scanned_percent": 100}
    uncovered = pipeline._get_uncovered_subregions(scanned_regions(pipeline), start, end)
    missing = sum(b - a for a, b in uncovered)
    data: Dict[str, Any] = {"scanned_percent": int(round(100 * (1 - missing / (end - start))))}
    if uncovered:
        data["unscanned"] = [f"{fmt_time(a)}-{fmt_time(b)}" for a, b in uncovered[:MAX_UNSCANNED_LISTED]]
        if len(uncovered) > MAX_UNSCANNED_LISTED:
            data["unscanned"].append(f"... and {len(uncovered) - MAX_UNSCANNED_LISTED} more")
        data["note"] = (
            "No cues in unscanned audio doesn't mean no silences there: scan_for_cues scans a chapter's span."
        )
    return data


def realign_search(pipeline) -> Optional[Dict[str, Any]]:
    """The window the realignment scanned around each reference chapter, and why it was that wide."""
    context = pipeline._realignment_context
    if context is None:
        return None
    padding = context.padding
    if padding > REALIGN_PADDING_EXPANDED:
        why = "twice the difference between the reference's length and the recording's, wider than thorough would scan"
    elif padding >= REALIGN_PADDING_EXPANDED:
        why = "thorough, or widened automatically after a weak first pass"
    else:
        why = f"the default; thorough=true scans ±{fmt_duration(REALIGN_PADDING_EXPANDED)}"
    return {"window": f"±{fmt_duration(padding)} around each reference chapter", "why": why}


def chapter_summary(pipeline, active: List[ChapterData]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "total": len(active),
        "excluded": sum(1 for c in active if not c.selected) or None,
        "transcribed": sum(1 for c in active if c.transcript) or None,
    }
    realigned = [c for c in active if c.realignment]
    if realigned:
        guesses = [c for c in realigned if c.realignment and c.realignment.is_guess and not c.realignment.pinned]
        summary["pinned"] = sum(1 for c in realigned if c.realignment and c.realignment.pinned)
        summary["guesses"] = len(guesses)
        summary["guess_ids"] = [short_id(c) for c in guesses[:MAX_GUESS_IDS]] or None
    return summary


def guesses_warning(pipeline) -> Optional[str]:
    realigned = [c for c in active_chapters(pipeline.chapters) if c.realignment]
    guesses = [c for c in realigned if c.realignment and c.realignment.is_guess and not c.realignment.pinned]
    if len(realigned) < MIN_REALIGNED or len(guesses) < MOSTLY_GUESSES * len(realigned):
        return None
    message = f"Most realigned chapters are unconfirmed guesses ({len(guesses)} of {len(realigned)})."
    context = pipeline._realignment_context
    if context is not None and context.padding < REALIGN_PADDING_EXPANDED:
        message += (
            " If starts are far from the reference's, or the book doesn't read its titles (so transcription can't "
            "confirm them), go_back to select_workflow and realign with thorough=true, which scans "
            f"±{fmt_duration(REALIGN_PADDING_EXPANDED)} around each chapter."
        )
    else:
        message += (
            " The search was already wide, so check guesses by listening, or the reference may not match this "
            "recording."
        )
    return message


def audio_end_warning(pipeline) -> Optional[str]:
    """A warning when chapters start at or after the end of the audio, which happens when the
    recording is missing audio that a reference covers (e.g. a copy cut short before the credits)."""
    duration = pipeline.book_duration
    beyond = [c for c in active_chapters(pipeline.chapters) if c.timestamp >= duration - BEYOND_AUDIO_MARGIN_SECONDS]
    if not beyond:
        return None
    listed = ", ".join(f"{short_id(c)} {quote(c.title)} at {fmt_time(c.timestamp)}" for c in beyond[:5])
    more = f" and {len(beyond) - 5} more" if len(beyond) > 5 else ""
    message = f"{len(beyond)} chapter(s) start at or after the end of the audio ({fmt_time(duration)}): {listed}{more}."
    context = pipeline._realignment_context
    if context is not None and context.ref_duration - duration >= MISSING_AUDIO_SECONDS:
        message += (
            f" The reference is {fmt_duration(context.ref_duration - duration)} longer than this recording, "
            "which may be missing its ending."
        )
    return message + " Delete them before submitting (check the last chapter that does have audio, too)."


def reference_length_warning(pipeline) -> Optional[str]:
    """A warning when the realignment's reference is much longer than the recording. Without
    transcription, the aligner squeezes the reference's last chapters into whatever audio is
    left rather than placing them past the end, so this is the only sign of a cut-short copy."""
    context = pipeline._realignment_context
    if context is None or context.ref_duration - pipeline.book_duration < MISSING_AUDIO_SECONDS:
        return None
    return (
        f"The reference is {fmt_duration(context.ref_duration - pipeline.book_duration)} longer than this "
        "recording. A different edition explains it if the difference is spread through the book; otherwise the "
        "recording may be missing audio at its start or end, and the reference's first or last chapters may not "
        "exist here. Listen to the first and last few chapters (low-confidence guesses especially)."
    )


def session_warnings(pipeline) -> List[str]:
    """Warnings about the chapters as a whole, for workflow results, list_chapters and the preview."""
    ordered = active_chapters(pipeline.chapters)
    if not pipeline.book or not ordered:
        return []
    # The end-of-audio warning already mentions the reference's length
    warnings = [
        w for w in [audio_end_warning(pipeline) or reference_length_warning(pipeline), guesses_warning(pipeline)] if w
    ]
    suspects = long_headings(ordered, pipeline.book_duration, pipeline.detected_cues)
    if suspects:
        numbers = [i + 1 for i, c in enumerate(ordered) if c.id in suspects]
        warnings.append(
            f"{len(suspects)} heading chapter(s) run much longer than the book's other headings and probably hide "
            f"an unmarked first section: chapters {numbers}. list_chapters shows where to look (`suspect`)."
        )
    return warnings


# ---------------------------------------------------------------------------
# Background jobs
# ---------------------------------------------------------------------------


class ShutdownFlag:
    """Set when the server starts shutting down (Ctrl+C, an update restart, a dev reload).

    The server waits for open requests to finish before it shuts the app down, so a tool
    waiting on long work would hold up the restart for its whole timeout. Waits check this
    and return at once instead.
    """

    def __init__(self) -> None:
        self.started = False


shutdown = ShutdownFlag()


class JobRunner:
    """The one long-running operation an MCP tool started, if any."""

    def __init__(self) -> None:
        self.task: Optional[asyncio.Task] = None
        self.label = ""
        self.error: Optional[str] = None
        self.started_at = 0.0
        self.finished_at = 0.0

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def start(self, label: str, work: Callable[[], Awaitable[Any]]) -> None:
        if self.running:
            raise ToolError(f"Still working on '{self.label}'. Call wait until it finishes.")
        self.label = label
        self.error = None
        self.started_at = time.time()
        self.task = asyncio.create_task(self._run(work))

    async def _run(self, work: Callable[[], Awaitable[Any]]) -> None:
        try:
            await work()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # The pipeline has already restarted at a safe step and shown the error in the UI
            logger.warning(f"MCP job '{self.label}' failed: {e}")
            self.error = str(e) or type(e).__name__
        finally:
            self.finished_at = time.time()


jobs = JobRunner()


def busy_reason(app_state: AppState) -> Optional[str]:
    """What Achew is working on, or None when the session is waiting for input."""
    if jobs.running:
        return jobs.label
    pipeline = app_state.pipeline
    if pipeline is None:
        return None
    if pipeline.step not in INTERACTIVE_STEPS:
        return pipeline.step.value
    if app_state.has_active_transcriptions:
        return "transcribing chapters"
    scan = pipeline._partial_scan_task
    if scan is not None and not scan.done():
        return "scanning for cues"
    return None


async def _report_progress(ctx: Optional[Context], app_state: AppState, last: Optional[tuple]) -> Optional[tuple]:
    progress = app_state.last_progress
    if ctx is None or not progress:
        return last
    key = (progress["step"], round(progress["percent"]), progress["message"])
    if key == last:
        return last
    try:
        message = f"{progress['step']}: {progress['message']}" if progress["message"] else progress["step"]
        await ctx.report_progress(float(progress["percent"]), 100.0, message)
    except Exception:
        # Progress is best-effort: clients that didn't ask for it may reject it
        pass
    return key


async def settle(app_state: AppState, ctx: Optional[Context], timeout: float) -> bool:
    """Wait until nothing is running or `timeout` seconds pass. True when settled."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, min(timeout, MAX_WAIT_SECONDS))
    last = None
    while busy_reason(app_state):
        if loop.time() >= deadline or shutdown.started:
            return False
        last = await _report_progress(ctx, app_state, last)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    return True


# ---------------------------------------------------------------------------
# Session snapshot
# ---------------------------------------------------------------------------


def book_summary(book) -> Dict[str, Any]:
    metadata = book.media.metadata
    return {
        "id": book.id,
        "title": metadata.title,
        "author": metadata.authorName or None,
        "duration": round(book.duration, 1),
        "length": fmt_duration(book.duration),
    }


def next_hint(app_state: AppState) -> str:
    step = session_step(app_state)
    pipeline = app_state.pipeline
    reason = busy_reason(app_state)
    if reason:
        if pipeline and pipeline.step == Step.REALIGN_VERIFICATION:
            return "Verifying the realignment by transcription. Call wait; finish_verification stops early."
        return f"Working ({reason}). Call wait until it finishes."
    if step in SETUP_STEPS:
        return f"Achew needs setup ({step.value}) before it can be used. The user needs to finish it in the web UI."
    if step == Step.IDLE or pipeline is None:
        return "No book is open. Find one with search_books or find_books_needing_cleanup, then call open_book."
    if step == Step.SELECT_WORKFLOW:
        return (
            "Inspect the references with get_references, then call start_workflow: realign (a reference has the "
            "right titles, timing is off), regenerate (timestamps are right, titles are bad), quick_edit (edit a "
            "reference as-is), or smart_detect (nothing usable; detect chapters from the audio)."
        )
    if step == Step.INITIAL_CHAPTER_SELECTION:
        return "Call get_detected_cues, then select_cues to choose which cues become chapters."
    if step == Step.CONFIGURE_ASR:
        if pipeline.pending_realign:
            return "Call configure_transcription with action 'transcribe' to verify the realignment, or 'skip'."
        return "Call configure_transcription: 'transcribe' to title chapters from the audio, or 'skip' to leave them."
    if step == Step.CHAPTER_EDITING:
        return (
            "Review with list_chapters and fix with edit_chapters (check boundaries with transcribe_audio and "
            "get_nearby_cues). When done, call preview_submission and then submit_to_audiobookshelf."
        )
    if step == Step.REVIEWING:
        return "Call submit_to_audiobookshelf, or go_back to chapter_editing to keep editing."
    if step == Step.COMPLETED:
        return "Chapters were saved to Audiobookshelf. Call close_session before opening another book."
    return "Call get_status."


def snapshot(app_state: AppState, since: Optional[float] = None) -> Dict[str, Any]:
    """The session's state as tools report it.

    `since` is when the calling tool started work: errors from before then are left out.
    """
    step = session_step(app_state)
    data: Dict[str, Any] = {"step": step.value}
    if app_state.step != step:
        # The user opened a settings page in the web UI; the session is unaffected
        data["ui_overlay"] = app_state.step.value

    reason = busy_reason(app_state)
    if reason:
        data["busy"] = True
        data["working_on"] = reason
        progress = app_state.last_progress
        if progress and progress["step"] == step.value:
            data["progress"] = {"percent": round(progress["percent"]), "message": progress["message"] or None}

    errors: List[str] = []
    cutoff = since if since is not None else time.time() - RECENT_ERROR_SECONDS
    if jobs.error and not jobs.running and jobs.finished_at >= cutoff:
        errors.append(jobs.error)
    if app_state.last_error and app_state.last_error[0] >= cutoff:
        message = app_state.last_error[1]
        if not any(message in e or e in message for e in errors):
            errors.append(message)
    if errors:
        data["error"] = " | ".join(errors)

    pipeline = app_state.pipeline
    if pipeline is not None:
        if pipeline.book:
            data["book"] = book_summary(pipeline.book)
        workflow = None
        if pipeline.is_realignment:
            workflow = "realign"
        elif pipeline.is_quick_edit:
            workflow = "quick_edit"
        data["workflow"] = workflow
        active = [c for c in pipeline.chapters if not c.deleted]
        if active:
            data["chapters"] = chapter_summary(pipeline, active)
            data["realign_search"] = realign_search(pipeline)
            data["can_undo"] = pipeline.can_undo()
            data["can_redo"] = pipeline.can_redo()
            data["warnings"] = session_warnings(pipeline) or None
        if pipeline.pending_realign:
            data["realign_pending"] = True
        elif pipeline.step == Step.CONFIGURE_ASR and pipeline.cues:
            # What configure_transcription's titles line up with (selection drops cues too close together)
            data["chapter_starts"] = [fmt_time(t) for t in pipeline.cues[:MAX_LISTED_STARTS]]
        # Typed List[str] but holds RestartStep members (a str enum). Going back to idle is
        # close_session, not go_back.
        options = [getattr(o, "value", o) for o in pipeline.get_restart_options()]
        options = [o for o in options if o != Step.IDLE.value]
        if options:
            data["go_back_options"] = options

    data["next"] = next_hint(app_state)
    if shutdown.started:
        data["next"] = "Achew is restarting. Wait a few seconds, then call get_status; unsaved edits are lost."
    return data


async def run_and_settle(
    label: str,
    work: Callable[[], Awaitable[Any]],
    ctx: Optional[Context],
    timeout: float,
) -> Dict[str, Any]:
    """Start `work` as the background job, wait for it to settle, and snapshot the session."""
    app_state = get_app_state()
    started = time.time()
    jobs.start(label, work)
    # Let the job take its first step before checking on it
    await asyncio.sleep(0)
    await settle(app_state, ctx, timeout)
    return snapshot(app_state, since=started)
