import logging
import mimetypes
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...app import get_app_state

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
