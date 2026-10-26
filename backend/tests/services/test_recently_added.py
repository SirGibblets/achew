"""Tests for the recently-added list shown on an empty Book Search (app/services/abs_service.py).

A stub ABS server returns a fixed set of items newest-first, the way the real
`sort=addedAt&desc=1` listing does, and records the params it was asked with.
"""

import time
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.services import abs_service as abs_module
from app.services.abs_service import (
    RECENTLY_ADDED_LIMIT,
    RECENTLY_ADDED_OVERFETCH,
    RECENTLY_ADDED_WINDOW_DAYS,
    ABSService,
)

DAY_MS = 86400 * 1000


def make_item(item_id: str, days_ago: float, has_audio: bool = True) -> dict:
    added = int(time.time() * 1000 - days_ago * DAY_MS)
    return {
        "id": item_id,
        "addedAt": added,
        "updatedAt": added,
        "media": {
            "metadata": {"title": item_id, "genres": [], "publishedYear": None, "description": None},
            "coverPath": "/cover.jpg",
            "numAudioFiles": 1 if has_audio else 0,
        },
    }


@pytest.fixture
async def abs_server(monkeypatch):
    state: dict = {"items": [], "params": None}

    async def list_items(request: web.Request) -> web.Response:
        state["params"] = dict(request.query)
        return web.json_response({"results": state["items"]})

    app = web.Application()
    app.router.add_get("/api/libraries/{library_id}/items", list_items)
    server = TestServer(app)
    await server.start_server()

    url = str(server.make_url("")).rstrip("/")
    monkeypatch.setattr(
        abs_module, "get_app_config", lambda: SimpleNamespace(abs=SimpleNamespace(url=url, api_key="k"))
    )

    yield state
    await server.close()


async def fetch(state: dict, items: list[dict]) -> list[str]:
    state["items"] = items
    async with ABSService() as service:
        return [book.id for book in await service.get_recently_added("lib")]


async def test_keeps_only_books_added_inside_the_window(abs_server):
    ids = await fetch(
        abs_server,
        [
            make_item("new", 1),
            make_item("edge", RECENTLY_ADDED_WINDOW_DAYS - 0.1),
            make_item("old", RECENTLY_ADDED_WINDOW_DAYS + 1),
        ],
    )
    assert ids == ["new", "edge"]


async def test_caps_the_list_and_keeps_newest_first(abs_server):
    items = [make_item(f"b{i}", i * 0.5) for i in range(RECENTLY_ADDED_LIMIT + 5)]
    ids = await fetch(abs_server, items)
    assert ids == [f"b{i}" for i in range(RECENTLY_ADDED_LIMIT)]


async def test_skips_items_without_audio(abs_server):
    ids = await fetch(abs_server, [make_item("ebook", 1, has_audio=False), make_item("audio", 2)])
    assert ids == ["audio"]


async def test_requests_newest_first_with_headroom_for_ebooks(abs_server):
    await fetch(abs_server, [])
    assert abs_server["params"] == {
        "sort": "addedAt",
        "desc": "1",
        "limit": str(RECENTLY_ADDED_LIMIT * RECENTLY_ADDED_OVERFETCH),
    }
