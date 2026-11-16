"""Tests for the MCP server's session and workflow tools (app/mcp_server/tools_session.py) and
the background-job plumbing behind them (app/mcp_server/runtime.py): long work returns
`busy` and `wait` picks it up, job errors reach the agent, and workflow inputs are checked
before anything starts."""

import asyncio

import pytest
from mcp_helpers import (
    call,
    call_error,
    connect,
    make_pipeline,
)

from app.api.routes.chapters import DetectedCue
from app.mcp_server.runtime import fmt_duration, fmt_time, parse_time
from app.models.enums import DetectionMode, Step
from app.models.references import TitleRefType
from app.services.processing_pipeline import PendingRealign


def test_times_round_trip():
    assert parse_time(90) == 90.0
    assert parse_time("90.5") == 90.5
    assert parse_time("1:30") == 90.0
    assert parse_time("1:02:03.5") == 3723.5
    assert fmt_time(3723.5) == "1:02:03.5"
    assert fmt_duration(59.6) == "1:00"
    assert fmt_duration(3723) == "1:02:03"
    with pytest.raises(ValueError):
        parse_time("soon")


async def test_open_book_refuses_while_another_book_is_open(app_state):
    app_state.pipeline = make_pipeline(step=Step.SELECT_WORKFLOW)
    async with connect() as client:
        error = await call_error(client, "open_book", item_id="item-2")
        assert "'Test Book' is already open" in error and "close_session" in error

        # Asking for the open book again just reports it
        data = await call(client, "open_book", item_id="item-1")
    assert data["already_open"] is True
    assert data["references"][0]["type"] == "abs"


async def test_long_work_returns_busy_and_wait_picks_it_up(app_state):
    pipeline = make_pipeline(step=Step.SELECT_WORKFLOW)
    app_state.pipeline = pipeline
    release = asyncio.Event()
    calls = []

    async def fake_start_workflow(workflow, ref_id, detection_mode, thorough, transcribe):
        calls.append((workflow, ref_id, detection_mode, thorough, transcribe))
        pipeline.step = Step.AUDIO_ANALYSIS
        app_state.last_progress = {"step": "audio_analysis", "percent": 42.0, "message": "Detecting cues"}
        await release.wait()
        pipeline.step = Step.INITIAL_CHAPTER_SELECTION

    pipeline.start_workflow = fake_start_workflow
    async with connect() as client:
        data = await call(client, "start_workflow", workflow="smart_detect", timeout_seconds=0.2)
        assert data["busy"] is True
        assert data["working_on"] == "smart_detect workflow"
        assert data["progress"] == {"percent": 42, "message": "Detecting cues"}
        assert "wait" in data["next"]

        # Only one job at a time
        assert "busy (smart_detect workflow)" in await call_error(client, "start_workflow", workflow="smart_detect")

        release.set()
        data = await call(client, "wait", timeout_seconds=5)
    assert data["step"] == "initial_chapter_selection"
    assert "busy" not in data
    assert calls == [("smart_detect", None, DetectionMode.AUTO, False, False)]


async def test_a_failed_job_reports_its_error(app_state):
    pipeline = make_pipeline(step=Step.SELECT_WORKFLOW)
    app_state.pipeline = pipeline

    async def failing_start_workflow(*args):
        raise RuntimeError("Unable to connect to Audiobookshelf server")

    pipeline.start_workflow = failing_start_workflow
    async with connect() as client:
        data = await call(client, "start_workflow", workflow="smart_detect", timeout_seconds=5)
    assert data["step"] == "select_workflow"
    assert data["error"] == "Unable to connect to Audiobookshelf server"


async def test_workflows_check_their_reference(app_state):
    pipeline = make_pipeline(step=Step.SELECT_WORKFLOW)
    app_state.pipeline = pipeline
    title_ref = next(r for r in pipeline.title_refs if r.type == TitleRefType.CUSTOM)
    async with connect() as client:
        assert "needs reference_id" in await call_error(client, "start_workflow", workflow="realign")
        assert "title reference" in await call_error(
            client, "start_workflow", workflow="quick_edit", reference_id=title_ref.id
        )
        assert "No chapter reference" in await call_error(
            client, "start_workflow", workflow="regenerate", reference_id="nope"
        )


def _cue_book(pipeline):
    """Nine long silences (real chapter breaks) among sixty short pauses."""
    real = [DetectedCue(timestamp=300.0 * (i + 1), gap=4.0 + i * 0.1) for i in range(9)]
    pauses = [DetectedCue(timestamp=37.0 + 50.0 * i, gap=0.6 + (i % 5) * 0.08) for i in range(60)]
    pipeline.detected_cues = sorted(real + pauses, key=lambda c: c.timestamp)
    return real


async def test_detected_cues_suggest_thresholds(app_state):
    pipeline = make_pipeline(step=Step.INITIAL_CHAPTER_SELECTION)
    app_state.pipeline = pipeline
    real = _cue_book(pipeline)
    async with connect() as client:
        data = await call(client, "get_detected_cues", max_cues=20)
    assert data["total_cues"] == 69
    assert len(data["cues"]) == 20
    assert data["listed"] == "20 of 69 (longest gaps)"
    # The sharpest drop in gap length sits right after the nine real breaks (ten chapters)
    assert any(b["chapters"] == 10 for b in data["natural_breaks"])
    assert data["reference_chapter_counts"] == {"Audiobookshelf": 4}
    by_count = {row["chapters"]: row["min_gap_seconds"] for row in data["thresholds"]}
    assert by_count[10] == round(min(c.gap for c in real), 2)
    assert by_count[4] == round(sorted((c.gap for c in real), reverse=True)[2], 2)


async def test_select_cues_snaps_to_cues_and_starts_at_zero(app_state):
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
        data = await call(client, "select_cues", min_gap_seconds=4.5, timestamps=["0:05:00.4", 1234.0])
    assert data["step"] == "configure_asr"
    assert data["snapped_to_cues"] == 1
    assert selected[0] == 0.0
    assert 300.0 in selected and 1234.0 in selected
    assert all(t in selected for t in [300.0 * (i + 1) for i in range(5, 9)])
    assert 1500.0 not in selected  # gap 4.4, under the threshold


async def test_configure_transcription_resumes_a_pending_realignment(app_state):
    pipeline = make_pipeline(step=Step.CONFIGURE_ASR)
    pipeline.pending_realign = PendingRealign(ref_id="r", detection_mode=DetectionMode.AUTO, thorough=False)
    app_state.pipeline = pipeline
    resumed = []

    async def fake_resume(transcribe):
        resumed.append(transcribe)
        pipeline.pending_realign = None
        pipeline.step = Step.CHAPTER_EDITING

    pipeline.resume_pending_realign = fake_resume
    async with connect() as client:
        assert "don't apply" in await call_error(client, "configure_transcription", action="skip", titles=["A"])
        data = await call(client, "configure_transcription", action="skip")
    assert resumed == [False]
    assert data["step"] == "chapter_editing"


async def test_go_back_only_to_offered_steps(app_state):
    pipeline = make_pipeline(step=Step.SELECT_WORKFLOW)
    app_state.pipeline = pipeline
    async with connect() as client:
        error = await call_error(client, "go_back", to_step="chapter_editing")
    assert "Can't go back to chapter_editing" in error


async def test_close_session_returns_everyone_to_book_search(app_state):
    app_state.pipeline = make_pipeline()
    async with connect() as client:
        data = await call(client, "close_session")
    assert app_state.pipeline is None
    assert data["step"] == "idle"


async def test_references_can_be_added_from_text(app_state):
    pipeline = make_pipeline(step=Step.SELECT_WORKFLOW)
    app_state.pipeline = pipeline
    async with connect() as client:
        added = await call(
            client, "add_reference_from_text", name="TOC", format="txt", content="Prologue\nThe Road\n\nEpilogue\n"
        )
        full = await call(client, "get_references", reference_id=added["added"]["id"])
        chapters = await call(client, "get_references", reference_id=pipeline.chapter_refs[0].id)
    assert added["added"]["kind"] == "titles"
    assert full["title_list"] == ["Prologue", "The Road", "Epilogue"]
    assert [c["title"] for c in chapters["chapter_list"]][:2] == ["Opening Credits", "Chapter 1"]


async def test_no_natural_breaks_without_a_sharp_drop(app_state):
    pipeline = make_pipeline(step=Step.INITIAL_CHAPTER_SELECTION)
    app_state.pipeline = pipeline
    # Gaps shrinking steadily, as in a scored full-cast production
    pipeline.detected_cues = [DetectedCue(timestamp=30.0 * (i + 1), gap=30.0 * 0.97**i) for i in range(100)]
    async with connect() as client:
        data = await call(client, "get_detected_cues")
    assert "natural_breaks" not in data
    assert data["thresholds"]


async def test_configure_asr_lists_the_chapter_starts_titles_map_to(app_state):
    pipeline = make_pipeline(step=Step.CONFIGURE_ASR)
    pipeline.cues = [0.0, 600.0, 1500.0]
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "get_status")
    assert data["session"]["chapter_starts"] == ["0:00:00.0", "0:10:00.0", "0:25:00.0"]


async def test_wait_returns_at_once_when_the_server_shuts_down(app_state):
    from app.mcp_server.runtime import jobs, shutdown

    pipeline = make_pipeline(step=Step.AUDIO_ANALYSIS)
    app_state.pipeline = pipeline
    never = asyncio.Event()
    jobs.start("smart_detect workflow", never.wait)

    async def stop_soon():
        await asyncio.sleep(0.2)
        shutdown.started = True

    try:
        async with connect() as client:
            stopper = asyncio.create_task(stop_soon())
            started = asyncio.get_running_loop().time()
            data = await call(client, "wait", timeout_seconds=30)
            await stopper
        assert asyncio.get_running_loop().time() - started < 5
        assert data["busy"] is True
        assert "restarting" in data["next"]
    finally:
        shutdown.started = False
