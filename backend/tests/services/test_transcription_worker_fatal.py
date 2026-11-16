"""The editor's transcription worker (AppState._transcription_worker) on an ASRFatalError: a
transcription service that can't work at all (e.g. its server is unreachable) stops the whole
queue with one error banner instead of failing every queued chapter in turn."""

import asyncio

import pytest

from app.app import AppState
from app.core import config as C
from app.models.chapter import ChapterData
from app.services.asr_service import ASRFatalError


class StubPipeline:
    def __init__(self):
        self.book = None
        self.chapters = [ChapterData(timestamp=t, title=f"Chapter {i}") for i, t in enumerate([0.0, 60.0, 120.0])]


class StubState:
    """Just what the worker touches; the worker runs as an unbound AppState method on it"""

    def __init__(self):
        self.pipeline = StubPipeline()
        self._transcription_queue = asyncio.Queue()
        self._transcription_cancel_event = asyncio.Event()
        self._transcription_statuses = {}
        self.snippet_calls = 0
        self.errors = []

    async def transcribe_snippet(self, *args, **kwargs):
        self.snippet_calls += 1
        raise ASRFatalError("Couldn't connect to http://asr.test/v1: Connection refused")

    async def broadcast_error(self, message):
        self.errors.append(message)

    async def _broadcast_transcribing_state(self):
        pass

    async def broadcast_chapter_update(self):
        pass

    async def broadcast_history_update(self):
        pass


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    monkeypatch.setattr(C, "_app_config", C.AppConfig())


async def test_fatal_error_stops_the_queue_with_one_banner():
    state = StubState()
    ids = [c.id for c in state.pipeline.chapters]
    await state._transcription_queue.put({"chapter_ids": ids, "is_batch": True})
    await state._transcription_queue.put({"chapter_ids": [ids[0]], "is_batch": False})

    await AppState._transcription_worker(state)  # type: ignore[arg-type]

    assert state.snippet_calls == 1
    assert state.errors == ["Transcription failed: Couldn't connect to http://asr.test/v1: Connection refused"]
    assert state._transcription_queue.empty()
    assert state._transcription_statuses == {}
    assert [c.title for c in state.pipeline.chapters] == ["Chapter 0", "Chapter 1", "Chapter 2"]
