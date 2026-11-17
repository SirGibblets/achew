"""Tests for the Apply Titles → By Similarity route (POST /chapters/title-similarity)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import chapters
from app.models.chapter import BasicChapter, ChapterData
from app.models.enums import Step
from app.models.references import ChapterReference, ChapterRefType, TitleReference, TitleRefType
from app.services.processing_pipeline import ProcessingPipeline


class StubAppState:
    def __init__(self, pipeline):
        self.pipeline = pipeline


@pytest.fixture
def pipeline(monkeypatch):
    pipeline = ProcessingPipeline("item-1", lambda *args, **kwargs: None)
    pipeline.step = Step.CHAPTER_EDITING
    pipeline.chapters = [
        ChapterData(timestamp=600.0, title="Chapter Two", transcript="Chapter Two. The Vanishing Glass."),
        ChapterData(timestamp=0.0, title="Chapter One", transcript="Chapter One. The Boy Who Lived."),
        ChapterData(timestamp=300.0, title="Deleted", transcript="Chapter Three.", deleted=True),
        ChapterData(timestamp=900.0, title="Mr and Mrs Dursley", transcript="Mr and Mrs Dursley of number four"),
    ]
    pipeline.chapter_refs = [
        ChapterReference(
            name="Audible",
            short_name="Audible",
            description="",
            type=ChapterRefType.AUDNEXUS,
            duration=1200.0,
            chapters=[
                BasicChapter(timestamp=0.0, title="Chapter 1: The Boy Who Lived"),
                BasicChapter(timestamp=500.0, title="Chapter 2: The Vanishing Glass"),
                BasicChapter(timestamp=1000.0, title="Chapter 3: The Letters from No One"),
            ],
        )
    ]
    pipeline.title_refs = [
        TitleReference(
            name="EPUB", short_name="EPUB", description="", type=TitleRefType.EPUB, titles=["One", "2. Glass"]
        )
    ]
    monkeypatch.setattr(chapters, "get_app_state", lambda: StubAppState(pipeline))
    yield pipeline
    pipeline.cleanup_all_files()


@pytest.fixture
def client(pipeline):
    app = FastAPI()
    app.include_router(chapters.router, prefix="/api")
    return TestClient(app)


def test_matches_chapters_in_book_order_and_changes_nothing(client, pipeline):
    response = client.post("/api/chapters/title-similarity", json={"ref_id": pipeline.chapter_refs[0].id})
    assert response.status_code == 200
    by_id = {c.id: c for c in pipeline.chapters}
    matches = [
        (by_id[m["chapter_id"]].title, m["ref_index"], m["title"], m["confident"]) for m in response.json()["matches"]
    ]
    assert matches == [
        ("Chapter One", 0, "Chapter 1: The Boy Who Lived", True),
        ("Chapter Two", 1, "Chapter 2: The Vanishing Glass", True),
    ]
    assert [c.title for c in pipeline.chapters] == ["Chapter Two", "Chapter One", "Deleted", "Mr and Mrs Dursley"]
    assert pipeline.history_stack == []


def test_title_references_work_too(client, pipeline):
    response = client.post("/api/chapters/title-similarity", json={"ref_id": pipeline.title_refs[0].id})
    assert response.status_code == 200
    assert [(m["ref_index"], m["title"]) for m in response.json()["matches"]] == [(0, "One"), (1, "2. Glass")]


def test_an_unknown_reference_is_404(client):
    response = client.post("/api/chapters/title-similarity", json={"ref_id": "nope"})
    assert response.status_code == 404
