"""Tests for refinements from an agent's test run of the MCP server: the session's own step
behind a settings page, chapters past the end of the audio, cue silence times, transcript
match flags, quote-tolerant search, pauses inside transcription windows, restored chapters
counting as confirmed, grouped short-chapter warnings, and explicit empty title preferences."""

import pytest
from mcp_helpers import DURATION, call, call_error, connect, make_book, make_pipeline

from app.api.routes.chapters import DetectedCue
from app.mcp_server import tools_editing, tools_library
from app.mcp_server.runtime import short_id
from app.models.abs import LibrarySearchHit, LibrarySearchResponse, MatchType
from app.models.chapter import BasicChapter, ChapterData, RealignmentData
from app.models.enums import Step
from app.models.references import ChapterReference, ChapterRefType
from app.services.processing_pipeline import RealignmentContext


def _by_title(pipeline, title):
    return next(c for c in pipeline.chapters if c.title == title and not c.deleted)


async def test_a_settings_page_in_the_ui_doesnt_hide_the_session_step(app_state):
    app_state.pipeline = make_pipeline()
    app_state.step = Step.ASR_SETUP  # the user opened Transcription Settings
    try:
        async with connect() as client:
            data = await call(client, "get_status")
    finally:
        app_state.step = None
    assert data["session"]["step"] == "chapter_editing"
    assert data["session"]["ui_overlay"] == "asr_setup"
    assert "list_chapters" in data["session"]["next"]


def _cut_short(pipeline):
    """A reference from a copy 20 minutes longer: its last two chapters land after the audio ends."""
    pipeline.chapters += [
        ChapterData(
            timestamp=t,
            title=title,
            realignment=RealignmentData(original_timestamp=t, confidence=0.5, is_guess=True),
        )
        for t, title in [(DURATION - 3.6, "Six"), (DURATION + 852.0, "Seven"), (DURATION + 1170.0, "End Credits")]
    ]
    pipeline._realignment_context = RealignmentContext(ref_duration=DURATION + 1230.0, padding=15.0)


async def test_chapters_past_the_end_of_the_audio_are_flagged(app_state):
    pipeline = make_pipeline()
    _cut_short(pipeline)
    app_state.pipeline = pipeline
    async with connect() as client:
        listed = await call(client, "list_chapters")
        status = await call(client, "get_status")
        preview = await call(client, "preview_submission")
        refused = await call_error(client, "submit_to_audiobookshelf", confirm=True)

    by_title = {c["title"]: c for c in listed["chapters"]}
    assert by_title["Six"]["length"] == "0:04"  # clamped to the end of the audio, not to "Seven"
    assert "beyond_audio" not in by_title["Six"]
    assert by_title["Seven"]["beyond_audio"] is True and by_title["Seven"]["length"] == "0:00"
    assert by_title["End Credits"]["beyond_audio"] is True

    warning = status["session"]["warnings"][0]
    assert "2 chapter(s) start at or after the end of the audio" in warning
    assert "20:30 longer" in warning
    assert preview["warnings"][0] == warning
    assert "start at or after the end of the audio" in refused
    assert pipeline.submitted is None


async def test_cues_say_where_their_silence_began(app_state):
    pipeline = make_pipeline()
    pipeline.detected_cues = [DetectedCue.from_silences(1497.0, 1501.0)]
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "get_nearby_cues", chapter_id=short_id(_by_title(pipeline, "Chapter 2")))
    cue = data["cues"][0]
    assert cue["time"] == "0:25:00.7"  # just before speech resumes
    assert cue["silence_from"] == "0:24:57.0"
    assert cue["gap"] == 4.0
    assert "resumes" in data["note"]


async def test_transcripts_are_marked_as_matching_or_not(app_state):
    pipeline = make_pipeline()
    _by_title(pipeline, "Chapter 1").transcript = "Chapter One. It was a bright cold day in April"
    _by_title(pipeline, "Chapter 2").transcript = "The clocks were striking thirteen"
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "list_chapters")
        everything = await call(client, "list_chapters", transcripts="all")
    by_title = {c["title"]: c for c in data["chapters"]}
    assert by_title["Chapter 1"]["transcript_matches"] is True and "transcript" not in by_title["Chapter 1"]
    assert by_title["Chapter 2"]["transcript_matches"] is False
    assert by_title["Chapter 2"]["transcript"] == "The clocks were striking thirteen"
    assert "transcript_matches" not in by_title["Chapter 3"]  # never transcribed
    assert data["transcribed"] == "2 of 4 chapters"
    assert "transcript" in {c["title"]: c for c in everything["chapters"]}["Chapter 1"]


class _FakeABS:
    """Audiobookshelf search that, like the real one, matches text literally."""

    def __init__(self, titles):
        self.books = [make_book(item_id=f"b{i}", title=t) for i, t in enumerate(titles)]
        self.queries = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get_libraries(self):
        return [{"id": "lib", "name": "Audiobooks", "mediaType": "book"}]

    async def search_library(self, library_id, query, limit):
        self.queries.append(query)
        hits = [
            LibrarySearchHit(book=b, match_type=MatchType.TITLE, match_text=b.media.metadata.title)
            for b in self.books
            if query.lower() in b.media.metadata.title.lower()
        ]
        return LibrarySearchResponse(hits=hits[:limit], total=len(hits))


@pytest.mark.parametrize(
    "query, expected",
    [
        ("No Man's Land", "No Man’s Land"),  # straight quote, curly title
        ("Les Miserables", "Les Misérables"),  # no accent typed
        ("Wonder - Year", "The Wonder — Year One"),  # dash typed differently, mid-title
    ],
)
async def test_search_tolerates_quotes_dashes_and_accents(app_state, monkeypatch, query, expected):
    fake = _FakeABS(["No Man’s Land", "Les Misérables", "The Wonder — Year One", "Other Book"])
    monkeypatch.setattr(tools_library, "ABSService", lambda: fake)
    async with connect() as client:
        data = await call(client, "search_books", query=query)
    assert [b["title"] for b in data["books"]] == [expected]
    assert data["searched_as"]


async def test_transcribe_audio_reports_pauses_and_doesnt_trim_by_default(app_state, monkeypatch):
    pipeline = make_pipeline()
    pipeline.detected_cues = [DetectedCue.from_silences(603.0, 606.7)]
    app_state.pipeline = pipeline
    calls = []

    async def fake_transcribe(start, duration, label="snippet", should_abort=None, trim=None):
        calls.append((start, duration, trim))
        return "And so it ended."

    monkeypatch.setattr(app_state, "transcribe_snippet", fake_transcribe)
    monkeypatch.setattr(tools_editing, "get_preferred_service", lambda: object())
    async with connect() as client:
        data = await call(client, "transcribe_audio", timestamps=[600.0], seconds=10)
        trimmed = await call(client, "transcribe_audio", timestamps=[600.0], seconds=10, trim=True)
    snippet = data["snippets"][0]
    assert calls[0] == (600.0, 10.0, False)
    assert snippet["pauses"] == [{"from": "0:10:03.0", "to": "0:10:06.7", "seconds": 3.7}]
    assert "trimmed_at_longest_pause" not in snippet
    assert calls[1][2] is True and trimmed["snippets"][0]["trimmed_at_longest_pause"] is True


async def test_adding_at_a_deleted_chapter_restores_it_as_confirmed(app_state):
    pipeline = make_pipeline(realigned=True)
    two = _by_title(pipeline, "Chapter 2")
    two.realignment = RealignmentData(original_timestamp=1495.0, confidence=0.4, is_guess=True)
    app_state.pipeline = pipeline
    async with connect() as client:
        await call(client, "edit_chapters", changes=[{"action": "delete", "id": short_id(two)}])
        data = await call(client, "edit_chapters", changes=[{"action": "add", "start": 1500.1, "title": ""}])
    assert data["applied"] == [
        f"restored deleted chapter {short_id(two)} (\u201cChapter 2\u201d) at 0:25:00.1, confirmed and pinned"
    ]
    assert not two.deleted
    assert two.timestamp == 1500.1
    assert two.realignment is not None
    assert (two.realignment.pinned, two.realignment.is_guess, two.realignment.confidence) == (True, False, 1.0)
    view = data["changed"][0]
    assert view["realign"]["pinned"] is True and "guess" not in view["realign"]


async def test_short_chapters_a_reference_also_has_are_grouped(app_state):
    pipeline = make_pipeline()
    # Part headings: a few seconds long, here and in the publisher's chapters
    for t, title in [(594.0, "Part One"), (1494.0, "Part Two")]:
        pipeline.chapters.append(ChapterData(timestamp=t, title=title))
    pipeline.chapters.append(ChapterData(timestamp=2395.0, title="Oops"))
    pipeline.chapters.sort(key=lambda c: c.timestamp)
    pipeline.chapter_refs.append(
        ChapterReference(
            type=ChapterRefType.AUDNEXUS,
            name="Audnexus",
            short_name="Audnexus",
            description="",
            chapters=[
                BasicChapter(timestamp=t, title=title)
                for t, title in [
                    (0.0, "Opening"),
                    (585.0, "Part 1"),
                    (592.0, "Chapter 1"),
                    (1487.0, "Part 2"),
                    (1493.0, "Chapter 2"),
                ]
            ],
            duration=DURATION,
        )
    )
    app_state.pipeline = pipeline
    async with connect() as client:
        preview = await call(client, "preview_submission")
    warnings = preview["warnings"]
    assert any(w.startswith("2 chapters are under 10 s, as in a reference") for w in warnings)
    assert any("\u201cOops\u201d" in w for w in warnings)
    assert not any("\u201cPart One\u201d" in w for w in warnings)


async def test_full_preview_lists_every_change(app_state):
    pipeline = make_pipeline()
    extra = [(2500.0 + 10.0 * i, f"Extra {i}") for i in range(70)]
    pipeline.chapters += [ChapterData(timestamp=t, title=f"Renamed {i}") for i, (t, _) in enumerate(extra)]
    pipeline.chapter_refs[0].chapters += [BasicChapter(timestamp=t, title=title) for t, title in extra]
    app_state.pipeline = pipeline
    async with connect() as client:
        short = await call(client, "preview_submission")
        full = await call(client, "preview_submission", full=True)
    assert short["retitled"] == 70
    assert short["changes"][-1] == "... and 10 more"
    assert len(full["changes"]) == 70


async def test_empty_title_preferences_say_so(app_state):
    async with connect() as client:
        data = await call(client, "get_status")
    assert data["title_preferences"].startswith("none set")


async def test_a_much_longer_reference_is_flagged_even_with_every_chapter_inside_the_audio(app_state):
    pipeline = make_pipeline(realigned=True)
    pipeline._realignment_context = RealignmentContext(ref_duration=DURATION + 1234.3, padding=15.0)
    app_state.pipeline = pipeline
    async with connect() as client:
        status = await call(client, "get_status")
        listed = await call(client, "list_chapters")
    warning = status["session"]["warnings"][0]
    assert warning.startswith("The reference is 20:34 longer than this recording")
    assert listed["warnings"] == [warning]
    assert not any(c.get("beyond_audio") for c in listed["chapters"])
