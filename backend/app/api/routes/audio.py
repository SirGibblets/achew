import asyncio
import logging
import mimetypes
import os
import subprocess
import tempfile
import threading
from typing import IO, Optional, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...app import get_app_state
from ...core.ffmpeg import ffmpeg_path
from ...services.audio_service import decoder_args

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_audio_mime_type(file_path: str) -> str:
    """Determine MIME type for audio file based on extension"""
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        # Default based on file extension
        file_path_lower = file_path.lower()
        if file_path_lower.endswith(".aac"):
            mime_type = "audio/aac"
        elif file_path_lower.endswith(".wav"):
            mime_type = "audio/wav"
        elif file_path_lower.endswith(".mp3"):
            mime_type = "audio/mpeg"
        elif file_path_lower.endswith(".m4b") or file_path_lower.endswith(".m4a"):
            mime_type = "audio/mp4"
        elif file_path_lower.endswith(".flac"):
            mime_type = "audio/flac"
        elif file_path_lower.endswith(".ogg"):
            mime_type = "audio/ogg"
        elif file_path_lower.endswith(".opus"):
            mime_type = "audio/opus"
        elif file_path_lower.endswith(".wma"):
            mime_type = "audio/x-ms-wma"
        else:
            mime_type = "audio/mpeg"  # Default fallback to MP3
    return mime_type


@router.get("/audio/stream")
async def stream_book_audio(request: Request):
    """Stream book audio from main file"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        if not app_state.pipeline.audio_file_path:
            raise HTTPException(status_code=404, detail="Book audio file not available")

        book_audio_path = app_state.pipeline.audio_file_path

        if not os.path.exists(book_audio_path):
            raise HTTPException(status_code=404, detail="Book audio file not found")

        file_size = os.path.getsize(book_audio_path)
        mime_type = _get_audio_mime_type(book_audio_path)

        range_header = request.headers.get("range")

        if range_header:
            try:
                range_match = range_header.replace("bytes=", "").split("-")
                start = int(range_match[0]) if range_match[0] else 0
                end = int(range_match[1]) if range_match[1] else file_size - 1

                start = max(0, start)
                end = min(file_size - 1, end)
                content_length = end - start + 1

                def generate_ranged_audio():
                    with open(book_audio_path, "rb") as audio_file:
                        audio_file.seek(start)
                        remaining = content_length
                        while remaining > 0:
                            chunk_size = min(8192, remaining)
                            chunk = audio_file.read(chunk_size)
                            if not chunk:
                                break
                            remaining -= len(chunk)
                            yield chunk

                return StreamingResponse(
                    generate_ranged_audio(),
                    status_code=206,
                    media_type=mime_type,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(content_length),
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
                )
            except (ValueError, IndexError):
                # Invalid range header, fall back to full file
                pass

        # Serve full file if no range or invalid range
        def generate_full_audio():
            with open(book_audio_path, "rb") as audio_file:
                while chunk := audio_file.read(8192):
                    yield chunk

        return StreamingResponse(
            generate_full_audio(),
            media_type=mime_type,
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stream book audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Longest stretch one playback preview transcodes. Previews are for checking whether
# the first seconds of audio are a chapter start, not for listening through a chapter;
# this also bounds a preview the browser never closes.
PREVIEW_MAX_SECONDS = 5 * 60

# The single preview transcode in flight. Starting a new preview (another play
# press) stops the previous one, so abandoned previews never pile up.
_preview_process: Optional[subprocess.Popen] = None
_preview_lock = threading.Lock()

# How much of a failed preview's ffmpeg error output to log
_PREVIEW_ERROR_TAIL_BYTES = 2000


def _kill_and_reap(process: subprocess.Popen) -> None:
    """Kill process if it's still running. Its exit is collected on a background thread,
    since wait() can block and this runs on the event loop."""
    if process.poll() is not None:
        return
    process.kill()
    threading.Thread(target=process.wait, daemon=True).start()


def _stop_preview_process() -> None:
    global _preview_process
    with _preview_lock:
        process, _preview_process = _preview_process, None
    if process is not None:
        _kill_and_reap(process)


def _read_tail(file: IO[bytes], limit: int) -> str:
    size = os.fstat(file.fileno()).st_size
    file.seek(max(0, size - limit))
    return file.read().decode("utf-8", errors="replace").strip()


@router.get("/audio/preview")
async def stream_preview_audio(start: float = 0.0):
    """Stream the book from `start` seconds as AAC-LC, transcoded on the fly.

    For audio browsers can't play: few decode xHE-AAC, so those books play through
    here (decoded with libfdk_aac). The stream begins at `start`, so the player
    plays it from 0 rather than seeking."""
    global _preview_process

    app_state = get_app_state()
    if not app_state.pipeline or not app_state.pipeline.audio_file_path:
        raise HTTPException(status_code=404, detail="Book audio file not available")
    book_audio_path = app_state.pipeline.audio_file_path
    if not os.path.exists(book_audio_path):
        raise HTTPException(status_code=404, detail="Book audio file not found")

    cmd = [
        ffmpeg_path(),
        "-nostdin",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, start):.3f}",
        *decoder_args(book_audio_path),
        "-i",
        book_audio_path,
        "-t",
        str(PREVIEW_MAX_SECONDS),
        "-map",
        "0:a:0",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-f",
        "adts",
        "pipe:1",
    ]

    _stop_preview_process()
    # ffmpeg's errors go to a file rather than a pipe: nothing reads stderr while audio
    # streams, and a full pipe would block ffmpeg mid-stream (the hang fixed for #24)
    stderr_file = tempfile.TemporaryFile()
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr_file)
    except OSError as e:
        stderr_file.close()
        logger.error(f"Failed to start audio preview: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    with _preview_lock:
        _preview_process = process

    async def generate_preview_audio():
        global _preview_process
        stdout = cast(IO[bytes], process.stdout)
        try:
            while chunk := await asyncio.to_thread(stdout.read, 64 * 1024):
                yield chunk
            returncode = await asyncio.to_thread(process.wait)
            with _preview_lock:
                superseded = _preview_process is not process
                if not superseded:
                    _preview_process = None
            # A preview stopped for a newer one exits nonzero too (exit code 1 on Windows)
            if returncode != 0 and not superseded:
                logger.error(
                    f"Audio preview from {start:.1f}s failed (ffmpeg exit {returncode}): "
                    f"{_read_tail(stderr_file, _PREVIEW_ERROR_TAIL_BYTES)}"
                )
        finally:
            # Also runs when the player stops or the page closes: Starlette cancels this
            # stream on disconnect, which a blocking sync generator would never notice
            _kill_and_reap(process)
            stderr_file.close()

    return StreamingResponse(
        generate_preview_audio(),
        media_type="audio/aac",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
