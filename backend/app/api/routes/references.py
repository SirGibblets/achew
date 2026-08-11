import logging
import os
import re
import tempfile
import time
import uuid
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ...app import get_app_state
from ...models.references import (
    BasicChapter,
    ChapterReference,
    ChapterRefType,
    TitleReference,
    TitleRefType,
)
from ...services.abs_service import ABSService
from ...services.audible_providers import region_for_provider
from ...services.reference_parsers import (
    csv_parser,
    cue_parser,
    epub_parser,
    json_parser,
    mobi_parser,
    text_parser,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Reference types that were auto-created and should not be deleted by the user
_AUTO_CHAPTER_REF_TYPES = {ChapterRefType.ABS, ChapterRefType.EMBEDDED, ChapterRefType.FILE_DATA}

# CUSTOM title reference is a singleton and should never be deleted
_PROTECTED_TITLE_TYPES = {TitleRefType.CUSTOM}

_SUPPORTED_EXTS = {".json", ".csv", ".cue", ".txt", ".epub", ".mobi", ".azw", ".azw3"}

# Where in-flight chunked uploads are assembled.
_UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "achew", "uploads")

# Upload ids come from the client and end up in a filename, so they are
# restricted to characters that cannot escape _UPLOAD_DIR.
_UPLOAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Ceiling on an assembled upload. Ebooks with cover art run large, so this only
# needs to be low enough to stop a client from filling the disk.
_MAX_UPLOAD_BYTES = 256 * 1024 * 1024

# Interrupted uploads leave a .part file behind; drop them once they're this old.
_STALE_PART_AGE_SEC = 30 * 60

# upload_id -> index of the chunk expected next, for uploads still in flight.
_expected_chunk: dict[str, int] = {}


def _part_path(upload_id: str) -> str:
    return os.path.join(_UPLOAD_DIR, f"{upload_id}.part")


def _discard_upload(upload_id: str) -> None:
    """Forget an upload and delete whatever has been assembled so far."""
    _expected_chunk.pop(upload_id, None)
    try:
        os.remove(_part_path(upload_id))
    except OSError:
        pass


def _sweep_stale_parts() -> None:
    """Delete part files from uploads that were abandoned partway through."""
    cutoff = time.time() - _STALE_PART_AGE_SEC
    try:
        names = os.listdir(_UPLOAD_DIR)
    except OSError:
        return
    for name in names:
        path = os.path.join(_UPLOAD_DIR, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                _expected_chunk.pop(name.removesuffix(".part"), None)
        except OSError:
            pass


def _parse_upload(pipeline, path: str, filename: str, ext: str):
    """Parse a fully assembled upload and attach it to the pipeline."""
    duration = pipeline.book.duration if pipeline.book else 0.0

    if ext == ".json":
        new_ref = json_parser.parse(path, ref_name=filename, duration=duration)
        pipeline.chapter_refs.append(new_ref)

    elif ext == ".csv":
        new_ref = csv_parser.parse(path, ref_name=filename, duration=duration)
        pipeline.chapter_refs.append(new_ref)

    elif ext == ".cue":
        new_ref = cue_parser.parse(path, ref_name=filename, duration=duration)
        pipeline.chapter_refs.append(new_ref)

    elif ext == ".txt":
        new_ref = text_parser.parse(path, ref_name=filename)
        pipeline.title_refs.append(new_ref)

    elif ext == ".epub":
        new_ref = epub_parser.parse(path, ref_name=filename)
        pipeline.title_refs.append(new_ref)

    elif ext in (".mobi", ".azw", ".azw3"):
        new_ref = mobi_parser.parse(path, ref_name=filename)
        pipeline.title_refs.append(new_ref)

    else:
        raise ValueError(f"Unsupported file type '{ext}'")

    return new_ref


class AddAudnexusRequest(BaseModel):
    asin: str
    provider: str = "audible"


class UpdateTitlesRequest(BaseModel):
    titles: List[str]


class ReferencesResponse(BaseModel):
    chapter_refs: List[ChapterReference]
    title_refs: List[TitleReference]


def _get_pipeline():
    app_state = get_app_state()
    if not app_state.pipeline:
        raise HTTPException(status_code=404, detail="No active pipeline")
    return app_state.pipeline


@router.get("/pipeline/references", response_model=ReferencesResponse)
async def get_references():
    """Get all chapter and title references for the active pipeline."""
    pipeline = _get_pipeline()
    return ReferencesResponse(
        chapter_refs=pipeline.chapter_refs,
        title_refs=pipeline.title_refs,
    )


@router.post("/pipeline/references/upload")
async def upload_reference(
    file: UploadFile = File(...),
    upload_id: str = Form(""),
    index: int = Form(0),
    total: int = Form(1),
):
    """Upload a file — optionally in ordered chunks — and parse it as a Reference.

    Ebook References run to megabytes while reverse proxies commonly cap request
    bodies at 1MB, so the client sends the file as a sequence of small chunks that
    are appended to one part file here. A plain single-request upload is just the
    degenerate case of one chunk, which is what omitting the chunk fields gives.

    Only the final chunk is parsed; earlier ones return how much has been received.
    """
    pipeline = _get_pipeline()
    app_state = get_app_state()

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()

    # Checked on every chunk, so an unsupported file is rejected on the first one
    # rather than after the whole thing has been uploaded.
    if ext not in _SUPPORTED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(_SUPPORTED_EXTS))}",
        )
    if total < 1 or index < 0 or index >= total:
        raise HTTPException(status_code=400, detail=f"Invalid chunk {index} of {total}")
    if upload_id and not _UPLOAD_ID_RE.match(upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload id")

    uid = upload_id or uuid.uuid4().hex
    os.makedirs(_UPLOAD_DIR, exist_ok=True)

    if index == 0:
        _sweep_stale_parts()
    elif _expected_chunk.get(uid) != index:
        # Chunks have to arrive in order to concatenate correctly; a gap means
        # this upload can't be trusted, so drop it and make the client restart.
        _discard_upload(uid)
        raise HTTPException(status_code=409, detail="Upload chunks arrived out of order")

    path = _part_path(uid)
    try:
        content = await file.read()
        with open(path, "wb" if index == 0 else "ab") as f:
            f.write(content)
        assembled_bytes = os.path.getsize(path)
    except OSError as e:
        _discard_upload(uid)
        logger.error(f"Failed to store upload {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to store uploaded file")

    if assembled_bytes > _MAX_UPLOAD_BYTES:
        _discard_upload(uid)
        # Deliberately not a 413 — the frontend reads that status as "something
        # in front of Achew rejected this", which would be misleading here.
        raise HTTPException(
            status_code=400,
            detail=f"File is too large (limit {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )

    if index + 1 < total:
        _expected_chunk[uid] = index + 1
        return {"upload_id": uid, "received": index + 1, "total": total}

    try:
        new_ref = _parse_upload(pipeline, path, filename, ext)
    except ValueError as e:
        logger.warning(f"Failed to parse uploaded file {filename}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error processing uploaded file {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process file")
    finally:
        _discard_upload(uid)

    await app_state.broadcast_references_update()
    return new_ref


@router.post("/pipeline/references/audnexus")
async def add_audnexus_reference(request: AddAudnexusRequest):
    """Fetch Audnexus chapter data for an ASIN and add it as a chapter reference."""
    pipeline = _get_pipeline()
    app_state = get_app_state()

    region = region_for_provider(request.provider) or "US"

    async with ABSService() as abs_service:
        chapter_data = await abs_service.get_audnexus_chapters(request.asin, region=region)

    if not chapter_data or not chapter_data.chapters:
        raise HTTPException(
            status_code=404,
            detail=f"No Audnexus chapter data found for ASIN {request.asin}",
        )

    chapters = [BasicChapter(timestamp=ch.startOffsetMs / 1000, title=ch.title) for ch in chapter_data.chapters]
    duration_sec = float(chapter_data.runtimeLengthMs) / 1000
    new_ref = ChapterReference(
        type=ChapterRefType.AUDNEXUS,
        name="Audnexus Chapters",
        short_name="Audnexus",
        description=f"Audnexus chapter data for ASIN {request.asin}",
        metadata={
            "ASIN": request.asin,
            "Duration": f"{int(duration_sec // 60)}m",
        },
        chapters=chapters,
        duration=duration_sec,
    )
    pipeline.chapter_refs.append(new_ref)

    await app_state.broadcast_references_update()
    return new_ref


@router.delete("/pipeline/references/{ref_id}")
async def delete_reference(ref_id: str):
    """Remove a user-added reference from the pipeline."""
    pipeline = _get_pipeline()
    app_state = get_app_state()

    # Check chapter references
    chapter_match = next((r for r in pipeline.chapter_refs if r.id == ref_id), None)
    if chapter_match:
        if chapter_match.type in _AUTO_CHAPTER_REF_TYPES:
            raise HTTPException(status_code=400, detail="Cannot delete auto-created References")
        pipeline.chapter_refs = [r for r in pipeline.chapter_refs if r.id != ref_id]
        await app_state.broadcast_references_update()
        return {"message": "Reference deleted"}

    # Check title references
    title_match = next((r for r in pipeline.title_refs if r.id == ref_id), None)
    if title_match:
        if title_match.type in _PROTECTED_TITLE_TYPES:
            raise HTTPException(status_code=400, detail="Cannot delete the custom Title Reference")
        pipeline.title_refs = [r for r in pipeline.title_refs if r.id != ref_id]
        await app_state.broadcast_references_update()
        return {"message": "Reference deleted"}

    raise HTTPException(status_code=404, detail="Reference not found")


@router.put("/pipeline/references/{ref_id}/titles")
async def update_reference_titles(ref_id: str, request: UpdateTitlesRequest):
    """Update the titles of the custom title reference."""
    pipeline = _get_pipeline()
    app_state = get_app_state()

    ref = next((r for r in pipeline.title_refs if r.id == ref_id), None)
    if not ref:
        raise HTTPException(status_code=404, detail="Title Reference not found")
    if ref.type != TitleRefType.CUSTOM:
        raise HTTPException(status_code=400, detail="Only the custom Title Reference can be edited")

    ref.titles = [t for t in request.titles if t.strip()]

    await app_state.broadcast_references_update()
    return ref
