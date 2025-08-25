import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List

from app.models.enums import Step
from app.models.progress import ProgressCallback

logger = logging.getLogger(__name__)


class ASRService(ABC):
    """Abstract base class for ASR services"""

    def __init__(self, progress_callback: ProgressCallback, model_path: str, language: str):
        self.progress_callback: ProgressCallback = progress_callback
        self.model_path: str = model_path
        self.language: str = language

    def _notify_progress(self, step: Step, percent: float, message: str = "", details: dict = None):
        """Notify progress via callback"""
        self.progress_callback(step, percent, message, details or {})

    @abstractmethod
    def _transcribe_file(self, audio_file: str) -> str:
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
        transcriptions = []
        total_files = len(audio_files)

        self._notify_progress(
            Step.ASR_PROCESSING,
            1,
            f"Starting {self.service_name} transcription of {total_files} chapters",
        )

        for i, audio_file in enumerate(audio_files):
            try:
                # Run transcription in thread pool
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._transcribe_file,
                    audio_file,
                )

                transcriptions.append(result)

                # Update progress
                progress = (i + 1) / total_files * 100
                self._notify_progress(
                    Step.ASR_PROCESSING,
                    progress,
                    f"Transcribed chapter {i + 1} of {total_files}...",
                    {
                        "completed_segments": i + 1,
                        "total_segments": total_files,
                    },
                )

            except Exception as e:
                logger.error(f"Failed to transcribe {audio_file}: {e}")
                transcriptions.append("[Transcription Error]")

        self._notify_progress(Step.ASR_PROCESSING, 100, "Transcription completed")
        return transcriptions

    @abstractmethod
    async def __aenter__(self):
        return self

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# Import the service options API - this will trigger plugin discovery
# noinspection PyUnresolvedReferences
from app.services.asr_service_options import (
    get_available_services,
    get_preferred_service,
    set_preferred_service,
    create_asr_service,
)

# Import providers to ensure auto-registration
try:
    import app.services.asr_providers
except ImportError as e:
    logger.warning(f"Failed to import ASR providers: {e}")
