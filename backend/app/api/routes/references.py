import logging
import os
import tempfile
import uuid
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
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
async def upload_reference(file: UploadFile = File(...)):
    """Upload a file and parse it as a chapter or title reference."""
    pipeline = _get_pipeline()
    app_state = get_app_state()

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()

    supported_exts = {".json", ".csv", ".cue", ".txt", ".epub", ".mobi", ".azw", ".azw3"}
    if ext not in supported_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(supported_exts))}",
        )

    # Save to a temp file
    tmp_path = os.path.join(tempfile.gettempdir(), "achew", f"upload_{uuid.uuid4()}{ext}")
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        duration = pipeline.book.duration if pipeline.book else 0.0

        if ext == ".json":
            new_ref = json_parser.parse(tmp_path, ref_name=filename, duration=duration)
            pipeline.chapter_refs.append(new_ref)

        elif ext == ".csv":
            new_ref = csv_parser.parse(tmp_path, ref_name=filename, duration=duration)
            pipeline.chapter_refs.append(new_ref)

        elif ext == ".cue":
            new_ref = cue_parser.parse(tmp_path, ref_name=filename, duration=duration)
            pipeline.chapter_refs.append(new_ref)

        elif ext == ".txt":
            new_ref = text_parser.parse(tmp_path, ref_name=filename)
            pipeline.title_refs.append(new_ref)

        elif ext == ".epub":
            new_ref = epub_parser.parse(tmp_path, ref_name=filename)
            pipeline.title_refs.append(new_ref)

        elif ext in (".mobi", ".azw", ".azw3"):
            new_ref = mobi_parser.parse(tmp_path, ref_name=filename)
            pipeline.title_refs.append(new_ref)

        else:
            new_ref = None

    except ValueError as e:
        logger.warning(f"Failed to parse uploaded file {filename}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error processing uploaded file {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process file")
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    if new_ref is None:
        raise HTTPException(status_code=400, detail="File could not be parsed into a Reference")

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
