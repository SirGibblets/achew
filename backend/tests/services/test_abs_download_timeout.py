"""Tests for ABS file-download timeouts (app/services/abs_service.py).

aiohttp's default session timeout caps every request at 300s total, which killed
large audiobook downloads over slow links partway through (issue #127). The
session default is shrunk here so a short, slow stream stands in for a long one.
"""

import asyncio
from types import SimpleNamespace

import aiohttp
import aiohttp.client
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.services import abs_service as abs_module
from app.services.abs_service import ABSService

CHUNKS = 6
CHUNK_DELAY = 0.2
PAYLOAD = b"x" * 1024


async def slow_download(request: web.Request) -> web.StreamResponse:
    resp = web.StreamResponse(headers={"Content-Length": str(CHUNKS * len(PAYLOAD))})
    await resp.prepare(request)
    for _ in range(CHUNKS):
        await asyncio.sleep(CHUNK_DELAY)
        await resp.write(PAYLOAD)
    await resp.write_eof()
    return resp


@pytest.fixture
async def abs_server(monkeypatch):
    app = web.Application()
    app.router.add_get("/api/items/{book_id}/file/{ino}/download", slow_download)
    server = TestServer(app)
    await server.start_server()

    url = str(server.make_url("")).rstrip("/")
    monkeypatch.setattr(
        abs_module, "get_app_config", lambda: SimpleNamespace(abs=SimpleNamespace(url=url, api_key="k"))
    )
    # The whole stream takes ~1.2s, well past this stand-in for the 300s default.
    monkeypatch.setattr(aiohttp.client, "DEFAULT_TIMEOUT", aiohttp.ClientTimeout(total=0.5, sock_connect=30))

    yield server
    await server.close()


@pytest.mark.usefixtures("abs_server")
async def test_audio_download_outlives_session_total_timeout(tmp_path):
    out = tmp_path / "audio.m4b"
    async with ABSService() as service:
        assert await service.download_audio_file("book", "ino", str(out))
    assert out.read_bytes() == PAYLOAD * CHUNKS


@pytest.mark.usefixtures("abs_server")
async def test_library_file_download_outlives_session_total_timeout(tmp_path):
    out = tmp_path / "book.epub"
    async with ABSService() as service:
        assert await service.download_file("book", "ino", str(out))
    assert out.read_bytes() == PAYLOAD * CHUNKS


@pytest.mark.usefixtures("abs_server")
async def test_download_still_aborts_when_stalled(tmp_path, monkeypatch):
    stalled = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=0.05)
    monkeypatch.setattr(abs_module, "DOWNLOAD_TIMEOUT", stalled)
    async with ABSService() as service:
        assert not await service.download_audio_file("book", "ino", str(tmp_path / "audio.m4b"))
