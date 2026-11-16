"""Tests for the third round of refinements from agents' test runs: workflow summaries (guesses,
pins, transcripts, the realign search window), scan coverage in the cue tools, transcript flags
that respect where titles came from, pinned chapters shown as confirmed, listing a library,
and transcribe_audio's chapter checks and error reporting."""

from mcp_helpers import DURATION, STARTS, call, call_error, connect, make_book, make_pipeline

from app.api.routes.chapters import DetectedCue
from app.mcp_server import tools_editing, tools_library
from app.mcp_server.runtime import short_id
from app.models.chapter import RealignmentData
from app.services.processing_pipeline import RealignmentContext


def _realigned(padding=15.0, guesses=3):
    pipeline = make_pipeline(realigned=True)
    pipeline.is_realignment = True
    pipeline._realignment_context = RealignmentContext(ref_duration=DURATION, padding=padding)
    for chapter in pipeline.chapters[1 : 1 + guesses]:
        chapter.realignment = RealignmentData(original_timestamp=chapter.timestamp, confidence=0.35, is_guess=True)
    return pipeline


async def test_workflow_results_summarize_guesses_and_the_search_window(app_state):
    pipeline = _realigned()
    pipeline.chapters[3].realignment.pinned = True  # the user confirmed one guess
    pipeline.chapters[1].transcript = "Chapter 1"
    app_state.pipeline = pipeline
    async with connect() as client:
        session = (await call(client, "get_status"))["session"]
    summary = session["chapters"]
    assert (summary["total"], summary["pinned"], summary["guesses"], summary["transcribed"]) == (4, 1, 2, 1)
    assert summary["guess_ids"] == [short_id(pipeline.chapters[1]), short_id(pipeline.chapters[2])]
    assert session["realign_search"]["window"] == "±0:15 around each reference chapter"
    assert "thorough=true" in session["realign_search"]["why"]
    assert any(w.startswith("Most realigned chapters are unconfirmed guesses (2 of 4)") for w in session["warnings"])


async def test_a_window_wider_than_thorough_says_why(app_state):
    pipeline = _realigned(padding=2468.6, guesses=0)
    app_state.pipeline = pipeline
    async with connect() as client:
        session = (await call(client, "get_status"))["session"]
    assert session["realign_search"]["window"] == "±41:09 around each reference chapter"
    assert "twice the difference" in session["realign_search"]["why"]
    assert not session.get("warnings")


async def test_cue_tools_report_what_was_scanned(app_state):
    pipeline = _realigned(guesses=0)  # realignment scanned ±15 s around each reference start
    app_state.pipeline = pipeline
    async with connect() as client:
        window = await call(client, "get_detected_cues", from_time=590, to_time=700)
        nearby = await call(client, "get_nearby_cues", chapter_id=short_id(pipeline.chapters[2]))
    assert window["scanned"]["scanned_percent"] == 23  # 590–615 of 590–700
    assert window["scanned"]["unscanned"] == ["0:10:15.0-0:11:40.0"]
    assert "doesn't mean no silences" in window["scanned"]["note"]
    assert nearby["scanned"]["scanned_percent"] < 10


async def test_a_full_scan_covers_everything(app_state):
    pipeline = make_pipeline()
    pipeline.normal_scanned_regions = [(0.0, DURATION)]  # smart detect scans the whole book
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "get_detected_cues", from_time=590, to_time=700)
    assert data["scanned"] == {"scanned_percent": 100}


async def test_reference_titles_that_equal_the_transcript_are_matches(app_state):
    pipeline = _realigned(guesses=0)
    pipeline.chapters[2].transcript = "Chapter 2"  # the reference title, heard exactly
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "list_chapters")
    view = data["chapters"][2]
    assert view["transcript_matches"] is True and "title_is_transcript" not in view


async def test_a_pinned_guess_shows_as_confirmed(app_state):
    pipeline = _realigned(guesses=1)
    app_state.pipeline = pipeline
    guess = pipeline.chapters[1]
    async with connect() as client:
        data = await call(client, "edit_chapters", changes=[{"action": "pin", "id": short_id(guess)}])
    assert data["changed"][0]["realign"] == {"pinned": True, "reference_start": STARTS[1]}


class _FakeLibrary:
    def __init__(self, titles):
        self.books = [make_book(item_id=f"b{i}", title=t) for i, t in enumerate(titles)]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get_library_items(self, library_id, use_cache=True):
        return list(self.books)


async def test_search_without_a_query_lists_a_library(app_state, monkeypatch):
    fake = _FakeLibrary(["Zebra", "Apple", "Éclair", "Mango"])
    monkeypatch.setattr(tools_library, "ABSService", lambda: fake)
    async with connect() as client:
        first = await call(client, "search_books", library_id="lib", limit=3)
        rest = await call(client, "search_books", library_id="lib", limit=3, offset=3)
        assert "library_id" in await call_error(client, "search_books")
    assert first["total"] == 4
    assert [b["title"] for b in first["books"]] == ["Apple", "Éclair", "Mango"]  # accents sort as letters
    assert first["next_offset"] == 3
    assert [b["title"] for b in rest["books"]] == ["Zebra"] and "next_offset" not in rest


async def test_checking_chapter_starts(app_state, monkeypatch):
    pipeline = make_pipeline()
    pipeline.detected_cues = [DetectedCue.from_silences(596.0, 600.3)]
    pipeline.normal_scanned_regions = [(0.0, DURATION)]
    app_state.pipeline = pipeline
    heard = {600.0: "Chapter One. It began", 1497.0: "and that was that. A new day"}

    async def fake_transcribe(start, duration, label="snippet", should_abort=None, trim=None):
        return heard[round(start, 1)]

    monkeypatch.setattr(app_state, "transcribe_snippet", fake_transcribe)
    monkeypatch.setattr(tools_editing, "get_preferred_service", lambda: object())
    one, two = pipeline.chapters[1], pipeline.chapters[2]
    async with connect() as client:
        data = await call(client, "transcribe_audio", chapter_ids=[short_id(one)])
        early = await call(client, "transcribe_audio", chapter_ids=[short_id(two)], lead_seconds=3)
        assert "either timestamps or chapter_ids" in await call_error(client, "transcribe_audio")
    snippet = data["snippets"][0]
    assert snippet["chapter"] == {"id": short_id(one), "title": "Chapter 1"}
    assert snippet["title_heard"] is True
    assert snippet["silence_before"] == {"gap": 4.3, "silence_from": "0:09:56.0"}
    lead = early["snippets"][0]
    assert lead["start"] == 1497.0 and lead["title_heard"] is False
    assert lead["silence_before"] == "none detected"


async def test_transcription_errors_say_what_went_wrong(app_state, monkeypatch):
    pipeline = make_pipeline()
    app_state.pipeline = pipeline

    async def failing(start, duration, label="snippet", should_abort=None, trim=None):
        if start > 3000:
            return None  # extraction found no audio
        raise RuntimeError("server returned 400: audio is empty")

    monkeypatch.setattr(app_state, "transcribe_snippet", failing)
    monkeypatch.setattr(tools_editing, "get_preferred_service", lambda: object())
    async with connect() as client:
        data = await call(client, "transcribe_audio", timestamps=[700, DURATION - 30])
    first, last = data["snippets"]
    assert first["error"] == "Transcription failed: RuntimeError: server returned 400: audio is empty"
    assert "shorter than its reported length" in last["error"]
