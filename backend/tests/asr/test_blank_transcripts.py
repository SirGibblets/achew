"""Blank transcriptions: non-speech annotations ([BLANK_AUDIO], [Music], ♪) count as no speech,
and a clip that trimming left blank is heard again untrimmed, by the editor's transcription worker
and by bulk transcription. (Realignment verification already did the latter.)"""

import asyncio

import pytest

from app.app import AppState
from app.core import config as C
from app.models.chapter import ChapterData
from app.models.enums import Step
from app.services import processing_pipeline as pipeline_module
from app.services.asr_service import ASRService, strip_non_speech


@pytest.mark.parametrize(
    "heard, expected",
    [
        ("[BLANK_AUDIO]", ""),
        (" [Music] Chapter One.", "Chapter One."),
        ("(upbeat music) Chapter Two", "Chapter Two"),
        ("♪ ♪", ""),
        ("Chapter 5 (continued)", "Chapter 5 (continued)"),  # parentheses that aren't a sound stay
    ],
)
def test_non_speech_annotations_are_stripped(heard, expected):
    assert strip_non_speech(heard) == expected


class _AnnotatingService(ASRService):
    """Says "[BLANK_AUDIO]" for the first clip, then real speech, like whisper.cpp on a silent start."""

    def __init__(self):
        self.calls = 0

    @property
    def service_name(self) -> str:
        return "test"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def _transcribe_file(self, audio_file: str, retry_on_empty: bool = True) -> str:
        self.calls += 1
        return "[BLANK_AUDIO]" if self.calls == 1 else "Chapter One."


def test_an_annotation_counts_as_blank_so_the_retries_run(monkeypatch, tmp_path):
    cropped = tmp_path / "cropped.wav"

    def crop(path, seconds):
        cropped.write_bytes(b"")
        return str(cropped)

    monkeypatch.setattr("app.services.audio_service.crop_start_to_tempfile", crop)
    service = _AnnotatingService()
    assert service._transcribe_with_jitter("clip.wav") == "Chapter One"
    assert service.calls == 2


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    monkeypatch.setattr(C, "_app_config", C.AppConfig())  # trim on by default


class _WorkerState:
    """Just what the transcription worker touches; trimmed clips come back blank."""

    def __init__(self):
        self.pipeline = type("P", (), {"book": None})()
        self.pipeline.chapters = [ChapterData(timestamp=0.0, title="Opening"), ChapterData(timestamp=60.0, title="")]
        self._transcription_queue = asyncio.Queue()
        self._transcription_cancel_event = asyncio.Event()
        self._transcription_statuses = {}
        self.calls = []

    async def transcribe_snippet(self, start, duration, label="snippet", should_abort=None, trim=None):
        self.calls.append(trim)
        return "Chapter 1 of Alice in Wonderland" if trim is False else ""

    async def broadcast_error(self, message):
        raise AssertionError(message)

    async def _broadcast_transcribing_state(self):
        pass

    async def broadcast_chapter_update(self):
        pass

    async def broadcast_history_update(self):
        pass


async def test_the_worker_hears_a_blank_trimmed_clip_again_untrimmed():
    state = _WorkerState()
    chapter = state.pipeline.chapters[1]
    state.pipeline.add_to_history = lambda op: None
    await state._transcription_queue.put({"chapter_ids": [chapter.id], "is_batch": False})

    await AppState._transcription_worker(state)  # type: ignore[arg-type]

    assert state.calls == [None, False]
    assert chapter.title == "Chapter 1 of Alice in Wonderland"


class _BulkService:
    """Transcribes trimmed clips as blank and untrimmed ones as speech."""

    def __init__(self):
        self.batches = []

    async def transcribe(self, files):
        self.batches.append(list(files))
        return ["" if f.endswith("_trimmed.wav") and f != "b_trimmed.wav" else f"heard {f}" for f in files]


async def test_bulk_transcription_hears_blank_trimmed_clips_again(monkeypatch):
    service = _BulkService()

    class _State:
        async def get_or_create_asr_service(self, progress_callback):
            return service

    monkeypatch.setattr(pipeline_module, "get_app_state", lambda: _State())
    pipeline = pipeline_module.ProcessingPipeline("item", lambda *args, **kwargs: None)
    try:
        pipeline.segment_files = ["a.wav", "b.wav", "c.wav"]
        pipeline.trimmed_segment_files = ["a_trimmed.wav", "b_trimmed.wav", "c_trimmed.wav"]
        # _notify_progress sets the step; transcription runs under ASR_PROCESSING
        transcripts = await pipeline._transcribe_segments()
    finally:
        pipeline.cleanup_all_files()

    assert pipeline.step == Step.ASR_PROCESSING
    assert service.batches == [pipeline.trimmed_segment_files, ["a.wav", "c.wav"]]
    assert transcripts == ["heard a.wav", "heard b_trimmed.wav", "heard c.wav"]
