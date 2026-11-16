"""Tests for refinements from an agent's run over LibriVox recordings: titles with track numbers
and titles heard after a preamble still match, the heading a snippet announces is reported,
chapters say whether they start on an audio file boundary, and credit chapters aren't flagged
as too short."""

from mcp_helpers import call, connect, make_pipeline

from app.mcp_server import tools_editing
from app.mcp_server.runtime import announced_heading, short_id, strip_track_prefix, transcript_matches_title
from app.models.chapter import ChapterData

LIBRIVOX = (
    "Chapter 1 of Alice's Adventures in Wonderland. This is a LibriVox recording. All LibriVox recordings are "
    "in the public domain. Chapter 1. Down the Rabbit-Hole."
)


def test_track_numbers_and_preambles_dont_hide_the_title():
    assert transcript_matches_title("01 - Chapter 1", LIBRIVOX)
    assert transcript_matches_title("Track 01 - Down the Rabbit-Hole", LIBRIVOX)  # heard after the preamble
    assert transcript_matches_title("001", "One. The Beginning")
    assert not transcript_matches_title("02 - Chapter 2", LIBRIVOX)
    # A number without a separator after it is part of the title, not a track number
    assert strip_track_prefix("12 Angry Men") == "12 Angry Men"
    assert strip_track_prefix("03_Chapter 3") == "Chapter 3"


def test_the_announced_heading_is_reported():
    assert announced_heading("Chapter 5 of Oliver Twist. This LibriVox recording is in the public domain") == (
        "Chapter 5"
    )
    assert announced_heading("Well then. Part Two. The Return") == "Part 2"
    assert announced_heading("It was a dark and stormy night") is None


async def test_snippets_report_the_heading_and_whether_the_title_was_heard(app_state, monkeypatch):
    pipeline = make_pipeline()
    pipeline.chapters[1].title = "01 - Chapter 1"
    app_state.pipeline = pipeline

    async def fake_transcribe(start, duration, label="snippet", should_abort=None, trim=None):
        return LIBRIVOX

    monkeypatch.setattr(app_state, "transcribe_snippet", fake_transcribe)
    monkeypatch.setattr(tools_editing, "get_preferred_service", lambda: object())
    async with connect() as client:
        data = await call(client, "transcribe_audio", chapter_ids=[short_id(pipeline.chapters[1])])
    snippet = data["snippets"][0]
    assert snippet["title_heard"] is True
    assert snippet["announces"] == "Chapter 1"


async def test_chapters_say_whether_they_start_on_a_file(app_state):
    pipeline = make_pipeline()
    pipeline.file_starts = [0.0, 600.4, 1700.0, 2400.0]  # chapter 2 (1500.0) doesn't sit on a file start
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "list_chapters")
    assert data["audio_files"] == 4
    assert [c["on_file_start"] for c in data["chapters"]] == [True, True, False, True]


async def test_single_file_books_dont_mention_files(app_state):
    pipeline = make_pipeline()
    pipeline.file_starts = [0.0]
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "list_chapters")
    assert "audio_files" not in data
    assert not any("on_file_start" in c for c in data["chapters"])


async def test_short_credit_chapters_arent_warned_about(app_state):
    pipeline = make_pipeline()
    pipeline.chapters += [ChapterData(timestamp=3591.0, title="End Credits"), ChapterData(timestamp=2395.0, title="x")]
    pipeline.chapters.sort(key=lambda c: c.timestamp)
    app_state.pipeline = pipeline
    async with connect() as client:
        preview = await call(client, "preview_submission")
    warnings = preview.get("warnings") or []
    assert not any("End Credits" in w for w in warnings)
    assert any("“x”" in w for w in warnings)
