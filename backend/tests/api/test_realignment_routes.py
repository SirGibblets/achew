"""Tests for the editor's pin and re-run realignment routes (app/api/routes/chapters.py)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import chapters
from app.api.routes.chapters import DetectedCue
from app.models.chapter import ChapterData, RealignmentData
from app.models.enums import Step
from app.services.processing_pipeline import ProcessingPipeline, RealignmentContext

REF = [0.0, 900.0, 1800.0, 2700.0]
TRUE = [0.0, 903.0, 1803.0, 2703.0]
DURATION = 3600.0


class _Pipeline(ProcessingPipeline):
    @property
    def book_duration(self) -> float:
        return DURATION


class StubAppState:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.broadcasts = 0

    async def broadcast_chapter_update(self):
        self.broadcasts += 1

    async def broadcast_history_update(self):
        pass


@pytest.fixture
def state(monkeypatch):
    pipeline = _Pipeline("item-1", lambda *args, **kwargs: None)
    pipeline.step = Step.CHAPTER_EDITING
    pipeline.detected_cues = [DetectedCue(timestamp=t, gap=3.0) for t in TRUE[1:]]
    pipeline._realignment_context = RealignmentContext(ref_duration=DURATION, padding=15.0)
    pipeline.chapters = [
        ChapterData(
            timestamp=t + (6.0 if i == 2 else 0.0),
            title=f"Chapter {i + 1}",
            realignment=RealignmentData(original_timestamp=r, confidence=0.85, is_guess=False),
        )
        for i, (r, t) in enumerate(zip(REF, TRUE))
    ]
    state = StubAppState(pipeline)
    monkeypatch.setattr(chapters, "get_app_state", lambda: state)
    yield state
    pipeline.cleanup_all_files()


@pytest.fixture
def client(state):
    app = FastAPI()
    app.include_router(chapters.router, prefix="/api")
    return TestClient(app)


def test_pin_and_unpin_are_undoable(client, state):
    chapter = state.pipeline.chapters[1]

    response = client.put(f"/api/chapters/{chapter.id}/pinned", json={"pinned": True})
    assert response.status_code == 200
    assert chapter.realignment.pinned

    client.put(f"/api/chapters/{chapter.id}/pinned", json={"pinned": False})
    assert not chapter.realignment.pinned

    state.pipeline.undo()
    assert chapter.realignment.pinned


def test_pinning_an_added_chapter_is_rejected(client, state):
    added = ChapterData(timestamp=1200.0, title="Added")
    state.pipeline.chapters.append(added)

    response = client.put(f"/api/chapters/{added.id}/pinned", json={"pinned": True})

    assert response.status_code == 400
    assert state.pipeline.history_stack == []


def test_realign_reports_what_moved(client, state):
    response = client.post("/api/chapters/realign")

    assert response.status_code == 200
    assert response.json()["realigned"] == 3
    assert response.json()["moved"] == 1
    assert [ch.timestamp for ch in state.pipeline.chapters] == pytest.approx(TRUE)
    assert state.broadcasts == 1


def test_realign_only_runs_while_editing(client, state):
    state.pipeline.step = Step.REVIEWING

    response = client.post("/api/chapters/realign")

    assert response.status_code == 400


def test_realign_with_everything_pinned_is_rejected(client, state):
    for chapter in state.pipeline.chapters[1:]:
        client.put(f"/api/chapters/{chapter.id}/pinned", json={"pinned": True})

    response = client.post("/api/chapters/realign")

    assert response.status_code == 400
    assert "pinned" in response.json()["detail"]
