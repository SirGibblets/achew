"""Tests for the /audio/preview transcode (app/api/routes/audio.py): how xHE-AAC books play
in the browser. Uses the xHE-AAC speech fixture from tests/audio/fixtures."""

import asyncio
import logging
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.routes import audio as audio_routes
from app.core.ffmpeg import ffmpeg_path, supports_xhe_aac

XHE_FIXTURE = Path(__file__).parent.parent / "audio" / "fixtures" / "xhe-aac-speech.m4a"

needs_fdk = pytest.mark.skipif(not supports_xhe_aac(), reason="ffmpeg in use lacks libfdk_aac")


@pytest.fixture
def book(tmp_path: Path, monkeypatch) -> Iterator[Path]:
    path = tmp_path / "book.m4b"
    shutil.copy(XHE_FIXTURE, path)
    state = SimpleNamespace(pipeline=SimpleNamespace(audio_file_path=str(path)))
    monkeypatch.setattr(audio_routes, "get_app_state", lambda: state)
    yield path
    audio_routes._stop_preview_process()


async def _drain(response) -> bytes:
    return b"".join([chunk async for chunk in response.body_iterator])


async def _wait_for_exit(process: subprocess.Popen) -> None:
    for _ in range(100):
        if process.poll() is not None:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("ffmpeg is still running")


def _duration(data: bytes, tmp_path: Path) -> float:
    path = tmp_path / "preview.aac"
    path.write_bytes(data)
    result = subprocess.run(
        [ffmpeg_path(), "-v", "error", "-i", str(path), "-f", "wav", "-"], capture_output=True, check=True
    )
    # 16-bit stereo 44.1 kHz PCM after the 44-byte header
    return (len(result.stdout) - 44) / (2 * 2 * 44100)


@needs_fdk
async def test_preview_streams_aac_from_start(book: Path, tmp_path: Path):
    data = await _drain(await audio_routes.stream_preview_audio(start=10.0))
    # ADTS frames start with a 12-bit sync word
    assert data[0] == 0xFF and data[1] & 0xF0 == 0xF0
    # The fixture is ~33.7 s long, so a preview from 10 s holds the remaining ~23.7 s
    assert 23.0 < _duration(data, tmp_path) < 24.5


@needs_fdk
async def test_closing_preview_stops_ffmpeg(book: Path):
    response = await audio_routes.stream_preview_audio(start=0.0)
    process = audio_routes._preview_process
    assert process is not None
    await response.body_iterator.__anext__()
    # What Starlette does when the player stops or the page closes
    await response.body_iterator.aclose()
    await _wait_for_exit(process)


@needs_fdk
async def test_new_preview_stops_previous(book: Path, caplog):
    first = await audio_routes.stream_preview_audio(start=0.0)
    first_process = audio_routes._preview_process
    assert first_process is not None
    await first.body_iterator.__anext__()

    second = await audio_routes.stream_preview_audio(start=5.0)
    await _wait_for_exit(first_process)
    with caplog.at_level(logging.ERROR, logger=audio_routes.logger.name):
        assert await _drain(second)
        # The stopped preview ends quietly: being replaced isn't a failure
        await _drain(first)
    assert not caplog.records


async def test_failed_preview_logs_ffmpeg_error(book: Path, caplog):
    book.write_bytes(b"not audio")
    with caplog.at_level(logging.ERROR, logger=audio_routes.logger.name):
        assert await _drain(await audio_routes.stream_preview_audio(start=0.0)) == b""
    assert any("Audio preview from 0.0s failed" in r.message and "ffmpeg exit" in r.message for r in caplog.records)
