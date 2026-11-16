"""Shared helpers for the MCP server tests: a real ProcessingPipeline holding a small book, and
an in-process MCP client. The fixtures that install them are in conftest.py."""

import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from mcp import Client

from app.api.routes.chapters import DetectedCue
from app.mcp_server import create_mcp_server
from app.models.abs import Book
from app.models.chapter import BasicChapter, ChapterData, RealignmentData
from app.models.enums import Step
from app.models.references import ChapterReference, ChapterRefType, TitleReference, TitleRefType
from app.services.processing_pipeline import ProcessingPipeline

DURATION = 3600.0
STARTS = [0.0, 600.0, 1500.0, 2400.0]
TITLES = ["Opening Credits", "Chapter 1", "Chapter 2", "Chapter 3"]


def make_book(item_id: str = "item-1", title: str = "Test Book", chapters: Optional[List[tuple]] = None) -> Book:
    return Book.model_validate(
        {
            "id": item_id,
            "addedAt": 0,
            "updatedAt": 0,
            "media": {
                "metadata": {
                    "title": title,
                    "authorName": "An Author",
                    "genres": [],
                    "publishedYear": None,
                    "description": None,
                },
                "coverPath": "",
                "duration": DURATION,
                "chapters": [{"title": t, "start": s, "end": e} for s, t, e in (chapters or [])],
            },
        }
    )


class _Pipeline(ProcessingPipeline):
    """A pipeline with no audio, so nothing touches ffmpeg or Audiobookshelf."""

    submitted: Optional[List[ChapterData]] = None

    async def submit_chapters(self, chapters):
        self.submitted = [c for c in chapters if c.selected]
        return True


def make_pipeline(step: Step = Step.CHAPTER_EDITING, realigned: bool = False) -> _Pipeline:
    pipeline = _Pipeline("item-1", lambda *args, **kwargs: None)
    pipeline.book = make_book()
    pipeline.step = step
    pipeline.chapters = [
        ChapterData(
            timestamp=t,
            title=title,
            realignment=RealignmentData(original_timestamp=t, confidence=0.9, is_guess=False) if realigned else None,
        )
        for t, title in zip(STARTS, TITLES)
    ]
    pipeline.chapter_refs = [
        ChapterReference(
            type=ChapterRefType.ABS,
            name="Audiobookshelf",
            short_name="ABS",
            description="Current chapters",
            chapters=[BasicChapter(timestamp=t, title=title) for t, title in zip(STARTS, TITLES)],
            duration=DURATION,
        )
    ]
    pipeline.title_refs = [
        TitleReference(type=TitleRefType.CUSTOM, name="Custom", short_name="Custom", description="", titles=[])
    ]
    pipeline.detected_cues = [DetectedCue(timestamp=t + 1.5, gap=2.5) for t in STARTS[1:]]
    return pipeline


@asynccontextmanager
async def connect():
    async with Client(create_mcp_server()) as client:
        yield client


async def call(client: Client, tool: str, **arguments: Any) -> Dict[str, Any]:
    """Call a tool that should succeed and return its JSON result."""
    response = await client.call_tool(tool, arguments)
    text = response.content[0].text  # type: ignore[union-attr]
    assert not response.is_error, text
    return json.loads(text)


async def call_error(client: Client, tool: str, **arguments: Any) -> str:
    """Call a tool that should fail and return its error message."""
    response = await client.call_tool(tool, arguments)
    text = response.content[0].text  # type: ignore[union-attr]
    assert response.is_error, text
    return text
