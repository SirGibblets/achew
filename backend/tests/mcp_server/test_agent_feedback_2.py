"""Tests for the second round of refinements from agents' test runs: the tools revision for stale
descriptions, cue exclusions/counts/windows, long-heading flags, whole short chapters in
transcribe_audio, section-number transcript matches, and compact replies for big edit batches."""

from mcp_helpers import call, connect, make_pipeline

from app.api.routes.chapters import DetectedCue
from app.mcp_server import create_mcp_server, tools_editing
from app.mcp_server.runtime import short_id, tools_revision, transcript_matches_title
from app.models.chapter import ChapterData
from app.models.enums import Step


async def test_the_tools_revision_tags_instructions_every_tool_and_status(app_state):
    async with connect() as client:
        data = await call(client, "get_status")
        tools = (await client.list_tools()).tools
    tag = f"[achew rev {tools_revision()}]"
    assert data["tools_revision"] == tools_revision()
    assert tag in (create_mcp_server().instructions or "")
    # Clients can cache tool schemas apart from the instructions, so each tool carries the tag too
    assert all((t.description or "").endswith(tag) for t in tools)
    # Docstrings are dedented, not sent with their source indentation
    assert not any("\n        " in (t.description or "") for t in tools)


def _cue_book(pipeline):
    """Ten real breaks (3–4 s) among short pauses, two of them long mid-chapter pauses."""
    real = [DetectedCue(timestamp=300.0 * (i + 1), gap=3.0 + i * 0.1) for i in range(10)]
    pauses = [DetectedCue(timestamp=37.0 + 50.0 * i, gap=0.6) for i in range(60)]
    long_pauses = [DetectedCue(timestamp=1234.0, gap=3.2), DetectedCue(timestamp=2345.0, gap=3.4)]
    pipeline.detected_cues = sorted(real + pauses + long_pauses, key=lambda c: c.timestamp)


async def test_select_cues_can_leave_out_pauses_above_the_threshold(app_state):
    pipeline = make_pipeline(step=Step.INITIAL_CHAPTER_SELECTION)
    app_state.pipeline = pipeline
    _cue_book(pipeline)
    selected = []

    async def fake_select(timestamps, include_unaligned=None):
        selected.extend(timestamps)
        pipeline.cues = list(timestamps)
        pipeline.step = Step.CONFIGURE_ASR

    pipeline.select_initial_chapters = fake_select
    async with connect() as client:
        data = await call(client, "select_cues", min_gap_seconds=2.9, exclude_timestamps=[1234.4, "0:39:05", 999.0])
    assert data["excluded"] == 2
    assert data["excludes_not_selected"] == [999.0]
    assert 1234.0 not in selected and 2345.0 not in selected
    assert len(selected) == 11  # 0:00 plus the ten real breaks


async def test_detected_cues_count_by_gap_and_list_a_window(app_state):
    pipeline = make_pipeline(step=Step.CHAPTER_EDITING)  # also usable in the editor
    app_state.pipeline = pipeline
    _cue_book(pipeline)
    async with connect() as client:
        everything = await call(client, "get_detected_cues", min_gap_seconds=2.9)
        window = await call(client, "get_detected_cues", from_time="0:15:00", to_time=1250, max_cues=3)
    assert everything["total_matching"] == 12
    at_least = {row["gap"]: row["cues"] for row in everything["cues_at_least"]}
    assert at_least[0.5] == 72 and at_least[3.0] == 12 and at_least[3.5] == 5
    assert window["total_matching"] == 10
    assert [c["start"] for c in window["cues"]] == [900.0, 1200.0, 1234.0]  # the 3 longest, in time order


def _sectioned_book(pipeline):
    """Short "Chapter N" headings, each followed by sections; Chapter 3's heading runs 10 minutes."""
    chapters = []
    t = 0.0
    for n in range(1, 6):
        heading = 600.0 if n == 3 else 20.0
        chapters.append(ChapterData(timestamp=t, title=f"Chapter {n}"))
        t += heading
        chapters.append(ChapterData(timestamp=t, title="One" if n != 3 else "Two"))
        t += 300.0
    pipeline.chapters = chapters
    pipeline.chapter_refs = []
    chapter_three = chapters[4].timestamp
    pipeline.detected_cues = [
        DetectedCue(timestamp=chapter_three + 0.8, gap=0.9),  # the heading's own pause
        DetectedCue(timestamp=chapter_three + 14.0, gap=1.49),  # the missed section start
        DetectedCue(timestamp=chapter_three + 70.0, gap=1.2),
    ]
    return chapters[4]


async def test_a_heading_that_runs_long_is_flagged_with_where_to_look(app_state):
    pipeline = make_pipeline()
    heading = _sectioned_book(pipeline)
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "list_chapters")
    flagged = {c["title"]: c for c in data["chapters"] if "suspect" in c}
    assert list(flagged) == ["Chapter 3"]
    message = flagged["Chapter 3"]["suspect"]
    assert "runs 10:00" in message and "typically 0:20" in message
    first_pause = heading.timestamp + 14.0
    assert f"{int(first_pause // 60) // 60}:{int(first_pause // 60) % 60:02d}" in message
    assert any("heading chapter(s) run much longer" in w for w in data["warnings"])


async def test_no_heading_flags_in_books_with_long_chapters(app_state):
    pipeline = make_pipeline()  # "Chapter N" chapters that are minutes long, as in most books
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "list_chapters")
    assert not any("suspect" in c for c in data["chapters"])


async def test_short_chapters_are_heard_whole(app_state, monkeypatch):
    pipeline = make_pipeline()
    pipeline.chapters.append(ChapterData(timestamp=622.0, title="Epigraph section"))  # 22 s after Chapter 1
    pipeline.chapters.sort(key=lambda c: c.timestamp)
    app_state.pipeline = pipeline
    lengths = []

    async def fake_transcribe(start, duration, label="snippet", should_abort=None, trim=None):
        lengths.append(round(duration, 1))
        return "Chapter One. As the poet said..."

    monkeypatch.setattr(app_state, "transcribe_snippet", fake_transcribe)
    monkeypatch.setattr(tools_editing, "get_preferred_service", lambda: object())
    async with connect() as client:
        await call(client, "transcribe_audio", timestamps=[600.0, 1500.0])
    assert lengths[0] == 21.5  # the whole 22 s chapter, stopping just short of the next
    assert lengths[1] == 15.0  # a long chapter: the user's transcription length, at least 15 s


def test_section_titles_match_their_number_alone():
    assert transcript_matches_title("Chapter 1.2", "Two. The guns fell silent")
    assert transcript_matches_title("Chapter 4.1", "1.")
    assert not transcript_matches_title("Chapter 1.2", "Three.")
    assert not transcript_matches_title("Chapter 12", "Two.")  # one number: not a section title


async def test_raw_transcript_titles_are_marked_as_such(app_state):
    pipeline = make_pipeline()
    pipeline.chapters[1].title = pipeline.chapters[1].transcript = "Chapter one, the beginning"
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "list_chapters")
    view = data["chapters"][1]
    assert view["title_is_transcript"] is True
    assert "transcript_matches" not in view


async def test_big_edit_batches_get_a_compact_reply(app_state):
    pipeline = make_pipeline()
    pipeline.chapters += [ChapterData(timestamp=2500.0 + 20.0 * i, title=f"x{i}") for i in range(30)]
    app_state.pipeline = pipeline
    changes = [
        {"action": "rename", "id": short_id(c), "title": f"Renamed {i}"} for i, c in enumerate(pipeline.chapters)
    ]
    async with connect() as client:
        data = await call(client, "edit_chapters", changes=changes)
    assert data["applied"] == {"rename": 34}
    assert len(data["first_changes"]) == 5
    assert "changed" not in data
    assert all(c.title.startswith("Renamed") for c in pipeline.chapters)


async def test_moving_a_chapter_clears_the_transcript_heard_at_its_old_start(app_state):
    pipeline = make_pipeline()
    moved, nudged = pipeline.chapters[1], pipeline.chapters[2]
    moved.transcript = "the end of the previous chapter"
    nudged.transcript = "Chapter 2"
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(
            client,
            "edit_chapters",
            changes=[
                {"action": "move", "id": short_id(moved), "start": 630.0},
                {"action": "move", "id": short_id(nudged), "start": 1500.4},  # a nudge keeps it
            ],
        )
        assert data["applied"][0].endswith("and cleared its old transcript")
        assert moved.transcript == "" and moved.title == "Chapter 1"
        assert nudged.transcript == "Chapter 2"
        await call(client, "undo")
    assert moved.transcript == "the end of the previous chapter" and moved.timestamp == 600.0


async def test_nearby_cues_are_capped_to_the_nearest(app_state):
    pipeline = make_pipeline()
    chapter = pipeline.chapters[2]  # 0:25:00, between chapters at 0:10:00 and 0:40:00
    pipeline.detected_cues = [DetectedCue(timestamp=605.0 + 10.0 * i, gap=0.5 + (i % 4) * 0.5) for i in range(170)]
    app_state.pipeline = pipeline
    async with connect() as client:
        default = await call(client, "get_nearby_cues", chapter_id=short_id(chapter))
        strong = await call(client, "get_nearby_cues", chapter_id=short_id(chapter), min_gap_seconds=2.0, max_cues=5)
    assert default["total_matching"] > 30 and len(default["cues"]) == 30
    offsets = [abs(c["offset"]) for c in default["cues"]]
    assert max(offsets) <= 150  # the 30 nearest, 10 s apart, either side
    assert [c["start"] for c in default["cues"]] == sorted(c["start"] for c in default["cues"])
    assert len(strong["cues"]) == 5 and all(c["gap"] >= 2.0 for c in strong["cues"])
