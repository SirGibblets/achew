import logging
import mimetypes
import os
import tempfile

from fastapi import APIRouter, HTTPException, Response
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


def _get_audio_format_info(file_path: str) -> tuple[str, str]:
    """Get format and MIME type for audio file"""
    file_path_lower = file_path.lower()

    if file_path_lower.endswith(".aac"):
        return "aac", "audio/aac"
    elif file_path_lower.endswith(".wav"):
        return "wav", "audio/wav"
    elif file_path_lower.endswith(".mp3"):
        return "mp3", "audio/mpeg"
    elif file_path_lower.endswith(".m4b"):
        return "m4b", "audio/mp4"
    elif file_path_lower.endswith(".m4a"):
        return "m4a", "audio/mp4"
    elif file_path_lower.endswith(".flac"):
        return "flac", "audio/flac"
    elif file_path_lower.endswith(".ogg"):
        return "ogg", "audio/ogg"
    elif file_path_lower.endswith(".opus"):
        return "opus", "audio/opus"
    elif file_path_lower.endswith(".wma"):
        return "wma", "audio/x-ms-wma"
    else:
        # Try to get MIME type and derive format
        mime_type = _get_audio_mime_type(file_path)
        format_name = mime_type.split("/")[-1] if "/" in mime_type else "unknown"
        return format_name, mime_type


def _get_chapter_and_segment_path(segment_id: str) -> tuple:
    """Common logic to get app state, chapter, and segment path"""
    app_state = get_app_state()

    if not app_state.pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Find the chapter by segment_id (which should be chapter_id)
    try:
        chapter_id = int(segment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid segment ID")

    chapter = None
    for ch in app_state.pipeline.chapters:
        if ch.id == chapter_id:
            chapter = ch
            break

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # Get the audio segment file path
    segment_path = chapter.audio_segment_path

    if not segment_path:
        raise HTTPException(status_code=404, detail="Audio segment path not configured")

    return app_state, chapter, segment_path


@router.get("/audio/segment/{segment_id}")
async def get_audio_segment(segment_id: str):
    """Stream audio segment for a chapter"""
    try:
        app_state, chapter, segment_path = _get_chapter_and_segment_path(segment_id)

        if not os.path.exists(segment_path):
            logger.error(f"Audio segment file does not exist: {segment_path}")
            # Log some debugging info about the temp directories
            sys_tmp_dir = tempfile.gettempdir()
            base_tmp_dir = os.path.join(sys_tmp_dir, "achew")
            logger.error(f"Base temp directory exists: {os.path.exists(base_tmp_dir)}")
            if os.path.exists(base_tmp_dir):
                try:
                    temp_dirs = [d for d in os.listdir(base_tmp_dir) if d.startswith("pipeline_")]
                    logger.error(f"Pipeline temp directories: {temp_dirs}")
                    for temp_dir in temp_dirs:
                        temp_dir_path = os.path.join(base_tmp_dir, temp_dir)
                        if os.path.exists(temp_dir_path):
                            files = os.listdir(temp_dir_path)
                            logger.error(f"Files in {temp_dir}: {files}")
                except Exception as e:
                    logger.error(f"Error listing temp directories: {e}")
            raise HTTPException(status_code=404, detail="Audio segment file not found")

        # Determine MIME type
        mime_type = _get_audio_mime_type(segment_path)

        # Stream the file
        def generate_audio():
            with open(segment_path, "rb") as audio_file:
                while chunk := audio_file.read(8192):
                    yield chunk

        file_size = os.path.getsize(segment_path)

        return StreamingResponse(
            generate_audio(),
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
        logger.error(f"Failed to get audio segment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audio/segments")
async def list_audio_segments():
    """List available audio segments for the current session"""
    try:
        app_state = get_app_state()

        if not app_state.pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        segments = []
        for chapter in app_state.pipeline.chapters:
            segment_info = {
                "segment_id": str(chapter.id),
                "chapter_id": chapter.id,
                "title": chapter.current_title,
                "timestamp": chapter.timestamp,
                "selected": chapter.selected,
                "url": f"/api/audio/segment/{chapter.id}",
                "available": bool(chapter.audio_segment_path and os.path.exists(chapter.audio_segment_path)),
            }

            # Add file info if available
            if chapter.audio_segment_path and os.path.exists(chapter.audio_segment_path):
                try:
                    file_size = os.path.getsize(chapter.audio_segment_path)
                    segment_info["file_size"] = file_size

                    # Determine format from extension
                    format_name, mime_type = _get_audio_format_info(chapter.audio_segment_path)
                    segment_info["format"] = format_name
                    segment_info["mime_type"] = mime_type

                except Exception as e:
                    logger.warning(f"Failed to get file info for {chapter.audio_segment_path}: {e}")

            segments.append(segment_info)

        return {
            "segments": segments,
            "total_segments": len(segments),
            "available_segments": len([s for s in segments if s["available"]]),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list audio segments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.head("/audio/segment/{segment_id}")
async def head_audio_segment(segment_id: str):
    """Get audio segment metadata without content"""
    try:
        app_state, chapter, segment_path = _get_chapter_and_segment_path(segment_id)

        if not os.path.exists(segment_path):
            raise HTTPException(status_code=404, detail="Audio segment not found")

        # Determine MIME type
        mime_type = _get_audio_mime_type(segment_path)

        file_size = os.path.getsize(segment_path)

        return Response(
            content=b"",
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
        logger.error(f"Failed to get audio segment metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))
