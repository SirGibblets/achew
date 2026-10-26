"""Tests for reusing an Add Chapter dialog snippet transcript (app/api/routes/chapters.py).

When the dialog already transcribed a candidate, "Add and transcribe" sends that transcript with
the add request instead of queueing ASR again. The transcript cache key tells the dialog when its
cached transcripts stop being valid.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import chapters
from app.core.config import ASROptions
from app.models.chapter import ChapterData


class StubPipeline:
    def __init__(self, instance_id="pipeline-1"):
        self.instance_id = instance_id
        self.chapters = [ChapterData(timestamp=0.0, title="Intro"), ChapterData(timestamp=600.0, title="Two")]
        self.history = []

    def add_to_history(self, operation):
        self.history.append(operation)


class StubAppState:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.enqueued = []

    async def broadcast_chapter_update(self):
        pass

    async def broadcast_history_update(self):
        pass

    async def enqueue_transcription(self, chapter_ids, is_batch=False):
        self.enqueued.append(chapter_ids)


@pytest.fixture
def state(monkeypatch):
    state = StubAppState(StubPipeline())
    monkeypatch.setattr(chapters, "get_app_state", lambda: state)
    return state


@pytest.fixture
def client(state):
    app = FastAPI()
    app.include_router(chapters.router, prefix="/api")
    return TestClient(app)


def _added(state):
    return next(c for c in state.pipeline.chapters if c.timestamp == 300.0)


def test_supplied_transcript_is_applied_without_queueing_asr(client, state):
    response = client.post("/api/chapters", json={"timestamp": 300.0, "transcribe": True, "transcript": "Chapter One"})

    assert response.status_code == 200
    added = _added(state)
    assert (added.title, added.transcript) == ("Chapter One", "Chapter One")
    assert state.enqueued == []


def test_supplied_transcript_undoes_with_the_add_in_one_step(client, state):
    client.post("/api/chapters", json={"timestamp": 300.0, "transcribe": True, "transcript": "Chapter One"})

    assert len(state.pipeline.history) == 1
    state.pipeline.history[0].undo(state.pipeline)
    assert [c.title for c in state.pipeline.chapters] == ["Intro", "Two"]


def test_empty_transcript_is_reused_for_no_speech(client, state):
    client.post("/api/chapters", json={"timestamp": 300.0, "title": "Ref title", "transcribe": True, "transcript": ""})

    # Matches what the transcription worker writes for a silent snippet
    assert (_added(state).title, _added(state).transcript) == ("", "")
    assert state.enqueued == []


def test_without_transcript_asr_is_queued(client, state):
    client.post("/api/chapters", json={"timestamp": 300.0, "transcribe": True})

    assert state.enqueued == [[_added(state).id]]
    assert _added(state).transcript == ""


class StubConfig:
    def __init__(self, **asr_options):
        self.asr_options = ASROptions(**asr_options)


def test_transcript_cache_key_tracks_pipeline_and_asr_settings(monkeypatch):
    config = StubConfig()
    asr_key = ("parakeet", "v3", "")
    monkeypatch.setattr(chapters, "get_app_config", lambda: config)
    monkeypatch.setattr(chapters, "get_asr_config_key", lambda: asr_key)

    pipeline = StubPipeline()
    baseline = chapters._transcript_cache_key(pipeline)
    assert chapters._transcript_cache_key(pipeline) == baseline

    assert chapters._transcript_cache_key(StubPipeline(instance_id="pipeline-2")) != baseline

    config.asr_options.segment_length = 12.0
    assert chapters._transcript_cache_key(pipeline) != baseline
    config.asr_options.segment_length = 8.0

    asr_key = ("whisper", "large", "en")
    assert chapters._transcript_cache_key(pipeline) != baseline
