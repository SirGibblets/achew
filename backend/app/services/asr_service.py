import asyncio
import logging
import os
import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.models.enums import Step
from app.models.progress import ProgressCallback

logger = logging.getLogger(__name__)


def _deduplicate_words(text: str) -> str:
    """De-duplicate consecutive repeated words (4+ occurrences).
    Single non-digit character repetitions are discarded entirely.
    Digit-only repetitions are de-duped regardless of length"""
    words = text.split()
    if len(words) < 2:
        return text

    result = []
    i = 0
    while i < len(words):
        word_lower = words[i].lower()
        j = i + 1
        while j < len(words) and words[j].lower() == word_lower:
            j += 1
        count = j - i

        if count >= 2 and words[i].isdigit():
            result.append(words[i])
        elif count >= 4:
            if len(words[i]) == 1:
                i = j
                continue
            result.append(words[i])
        else:
            result.extend(words[i:j])

        i = j

    return " ".join(result)


class ASRFatalError(RuntimeError):
    """The service can't transcribe anything right now (unreachable, credentials rejected,
    misconfigured). Stops a batch with this message instead of failing every chapter in turn."""


class ASRService(ABC):
    """Abstract base class for ASR services"""

    # How many files transcribe() works on at once. Local models handle one at a time;
    # a hosted service can keep several requests in flight.
    parallel_requests: int = 1

    @classmethod
    def config_key(cls) -> tuple:
        """Settings beyond service/variant/language that change this service's results;
        a change replaces the warm instance and invalidates cached snippet transcripts."""
        return ()

    def __init__(self, progress_callback: ProgressCallback, model_path: str, language: str):
        self.progress_callback: ProgressCallback = progress_callback
        self.model_path: str = model_path
        self.language: str = language

    def _notify_progress(self, step: Step, percent: float, message: str = "", details: Optional[Dict[str, Any]] = None):
        """Notify progress via callback"""
        self.progress_callback(step, percent, message, details or {})

    def _clean_transcription(self, result: str) -> str:
        return _deduplicate_words(result.strip(". \t\n\r\x0b\x0c"))

    def transcribe_file(self, audio_file: str) -> str:
        from app.services.audio_service import decodable_audio

        # ASR libraries decode with their own ffmpeg call, which can't take the
        # libfdk_aac options xHE-AAC needs, so they get a plain WAV for those files
        with decodable_audio(audio_file) as decodable_file:
            return self._transcribe_with_jitter(decodable_file)

    def _transcribe_with_jitter(self, audio_file: str) -> str:
        from app.core.constants import MAX_JITTER_CROP, MAX_JITTER_RETRIES
        from app.services.audio_service import crop_start_to_tempfile

        result = self._clean_transcription(self._transcribe_file(audio_file))
        if result:
            return result

        for _ in range(MAX_JITTER_RETRIES):
            crop_seconds = random.uniform(0.0, MAX_JITTER_CROP)
            jittered_file = crop_start_to_tempfile(audio_file, crop_seconds)
            if jittered_file is None:
                continue
            try:
                result = self._clean_transcription(self._transcribe_file(jittered_file, retry_on_empty=False))
                if result:
                    return result
            finally:
                try:
                    os.remove(jittered_file)
                except OSError:
                    pass

        return ""

    @abstractmethod
    def _transcribe_file(self, audio_file: str, retry_on_empty: bool = True) -> str:
        """Transcribe a single audio file - implemented by subclasses"""
        pass

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Name of the service for progress messages"""
        pass

    @property
    def bias_words(self) -> str:
        """Get bias words from ASR options"""
        try:
            from app.core.config import get_app_config

            config = get_app_config()
            if config.asr_options.use_bias_words:
                return config.asr_options.bias_words
            else:
                return ""
        except Exception as e:
            logger.warning(f"Failed to get bias words from config: {e}")
            return ""

    async def transcribe(self, audio_files: List[str]) -> List[str]:
        """Common transcription logic for all ASR services"""
        total_files = len(audio_files)
        transcripts: List[str] = [""] * total_files
        completed = 0
        limit = asyncio.Semaphore(max(1, self.parallel_requests))
        loop = asyncio.get_event_loop()

        self._notify_progress(
            Step.ASR_PROCESSING,
            1,
            f"Starting {self.service_name} transcription of {total_files} chapters",
        )

        async def transcribe_one(index: int, audio_file: str) -> None:
            nonlocal completed
            result: Optional[str]
            async with limit:
                try:
                    # Run transcription in thread pool
                    result = await loop.run_in_executor(None, self.transcribe_file, audio_file)
                except ASRFatalError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to transcribe {audio_file}: {e}")
                    result = None

            transcripts[index] = "[Transcription Error]" if result is None else result
            completed += 1
            details: Dict[str, Any] = {"completed_segments": completed, "total_segments": total_files}
            if result is not None:
                details["feed_text"] = f"\u201c{result}\u201d"
            self._notify_progress(
                Step.ASR_PROCESSING,
                completed / total_files * 100,
                f"Transcribed chapter {completed} of {total_files}…",
                details,
            )

        # Waiters acquire the semaphore in creation order, so one at a time keeps file order
        tasks = [asyncio.ensure_future(transcribe_one(i, f)) for i, f in enumerate(audio_files)]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            raise

        self._notify_progress(Step.ASR_PROCESSING, 100, "Transcription completed")
        return transcripts

    @abstractmethod
    async def __aenter__(self):
        return self

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# Import the service options API - this will trigger plugin discovery
# noinspection PyUnresolvedReferences

# Import providers to ensure auto-registration
try:
    import app.services.asr_providers  # noqa: F401
except ImportError as e:
    logger.warning(f"Failed to import ASR providers: {e}")
