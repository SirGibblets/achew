import logging
import os
import tempfile
import uuid
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ...app import get_app_state
from ...services.abs_service import ABSService
from ...models.sources import (
    CueSourceType,
    ExistingCue,
    ExistingCueSource,
    ExistingTitleSource,
    TitleSourceType,
)
from ...services.source_parsers import (
    csv_parser,
    cue_parser,
    epub_parser,
    json_parser,
    text_parser,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Source types that were auto-created and should not be deleted by the user
_AUTO_CUE_TYPES = {CueSourceType.ABS, CueSourceType.EMBEDDED, CueSourceType.FILE_DATA}

# CUSTOM source is a singleton and should never be deleted
_PROTECTED_TITLE_TYPES = {TitleSourceType.CUSTOM}


class AddAudnexusRequest(BaseModel):
    asin: str
    provider: str = "audible"


class UpdateTitlesRequest(BaseModel):
    titles: List[str]


class SourcesResponse(BaseModel):
    cue_sources: List[ExistingCueSource]
    title_sources: List[ExistingTitleSource]


def _get_pipeline():
    app_state = get_app_state()
    if not app_state.pipeline:
        raise HTTPException(status_code=404, detail="No active pipeline")
    return app_state.pipeline


@router.get("/pipeline/sources", response_model=SourcesResponse)
async def get_sources():
    """Get all cue and title sources for the active pipeline."""
    pipeline = _get_pipeline()
    return SourcesResponse(
        cue_sources=pipeline.existing_cue_sources,
        title_sources=pipeline.existing_title_sources,
    )


@router.post("/pipeline/sources/upload")
async def upload_source(file: UploadFile = File(...)):
    """Upload a file and parse it as a cue or title source."""
    pipeline = _get_pipeline()
    app_state = get_app_state()

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()

    supported_exts = {".json", ".csv", ".cue", ".txt", ".epub"}
    if ext not in supported_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(supported_exts))}",
        )

    # Save to a temp file
    tmp_path = os.path.join(
        tempfile.gettempdir(), "achew", f"upload_{uuid.uuid4()}{ext}"
    )
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        duration = pipeline.book.duration if pipeline.book else 0.0

        if ext == ".json":
            new_source = json_parser.parse(tmp_path, source_name=filename, duration=duration)
            pipeline.existing_cue_sources.append(new_source)

        elif ext == ".csv":
            new_source = csv_parser.parse(tmp_path, source_name=filename, duration=duration)
            pipeline.existing_cue_sources.append(new_source)

        elif ext == ".cue":
            new_source = cue_parser.parse(tmp_path, source_name=filename, duration=duration)
            pipeline.existing_cue_sources.append(new_source)

        elif ext == ".txt":
            new_source = text_parser.parse(tmp_path, source_name=filename)
            pipeline.existing_title_sources.append(new_source)

        elif ext == ".epub":
            new_source = epub_parser.parse(tmp_path, source_name=filename)
            pipeline.existing_title_sources.append(new_source)

        else:
            new_source = None

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

    if new_source is None:
        raise HTTPException(status_code=400, detail="File could not be parsed into a source")

    await app_state.broadcast_sources_update()
    return new_source


@router.post("/pipeline/sources/audnexus")
async def add_audnexus_source(request: AddAudnexusRequest):
    """Fetch Audnexus chapter data for an ASIN and add it as a cue source."""
    pipeline = _get_pipeline()
    app_state = get_app_state()

    region = request.provider.split(".")[-1].upper() if request.provider and "." in request.provider else "US"

    async with ABSService() as abs_service:
        chapter_data = await abs_service.get_audnexus_chapters(request.asin, region=region)

    if not chapter_data or not chapter_data.chapters:
        raise HTTPException(
            status_code=404,
            detail=f"No Audnexus chapter data found for ASIN {request.asin}",
        )

    cues = [
        ExistingCue(timestamp=ch.startOffsetMs / 1000, title=ch.title)
        for ch in chapter_data.chapters
    ]
    duration_sec = float(chapter_data.runtimeLengthMs) / 1000
    new_source = ExistingCueSource(
        type=CueSourceType.AUDNEXUS,
        name="Audnexus Chapters",
        short_name="Audnexus",
        description=f"Audnexus chapter data for ASIN {request.asin}",
        metadata={
            "ASIN": request.asin,
            "Duration": f"{int(duration_sec // 60)}m",
        },
        cues=cues,
        duration=duration_sec,
    )
    pipeline.existing_cue_sources.append(new_source)

    await app_state.broadcast_sources_update()
    return new_source


@router.delete("/pipeline/sources/{source_id}")
async def delete_source(source_id: str):
    """Remove a user-added source from the pipeline."""
    pipeline = _get_pipeline()
    app_state = get_app_state()

    # Check cue sources
    cue_match = next((s for s in pipeline.existing_cue_sources if s.id == source_id), None)
    if cue_match:
        if cue_match.type in _AUTO_CUE_TYPES:
            raise HTTPException(status_code=400, detail="Cannot delete auto-created sources")
        pipeline.existing_cue_sources = [s for s in pipeline.existing_cue_sources if s.id != source_id]
        await app_state.broadcast_sources_update()
        return {"message": "Source deleted"}

    # Check title sources
    title_match = next((s for s in pipeline.existing_title_sources if s.id == source_id), None)
    if title_match:
        if title_match.type in _PROTECTED_TITLE_TYPES:
            raise HTTPException(status_code=400, detail="Cannot delete the custom title source")
        pipeline.existing_title_sources = [s for s in pipeline.existing_title_sources if s.id != source_id]
        await app_state.broadcast_sources_update()
        return {"message": "Source deleted"}

    raise HTTPException(status_code=404, detail="Source not found")


@router.put("/pipeline/sources/{source_id}/titles")
async def update_source_titles(source_id: str, request: UpdateTitlesRequest):
    """Update the titles of the custom title source."""
    pipeline = _get_pipeline()
    app_state = get_app_state()

    source = next((s for s in pipeline.existing_title_sources if s.id == source_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="Title source not found")
    if source.type != TitleSourceType.CUSTOM:
        raise HTTPException(status_code=400, detail="Only the custom title source can be edited")

    source.titles = [t for t in request.titles if t.strip()]

    await app_state.broadcast_sources_update()
    return source
