"""
Parakeet ASR Service Provider

This module provides CPU-based Parakeet ASR services using the onnx-asr library, with auto-registration.
"""

import logging

import librosa
import numpy as np

from app.models.enums import Step
from app.models.progress import ProgressCallback
from app.services.asr_service import ASRService
from app.services.asr_service_options import register_asr_service, ASRModelVariant

logger = logging.getLogger(__name__)


class ParakeetASRService(ASRService):
    """ASR service using Parakeet via the onnx-asr library"""

    def __init__(
        self,
        progress_callback: ProgressCallback,
        model_path: str = "nemo-parakeet-tdt-0.6b-v2",
        language: str = "",
    ):
        super().__init__(progress_callback, model_path, language)
        self.model = None
        self.processor = None

    @property
    def service_name(self) -> str:
        return "Parakeet"

    async def __aenter__(self):
        """Initialize the ASR model"""
        try:
            import onnx_asr

            self._notify_progress(Step.ASR_PROCESSING, 0, "Loading Parakeet ASR model...")
            self.model = onnx_asr.load_model(self.model_path)
            self._notify_progress(Step.ASR_PROCESSING, 0, "Parakeet ASR model loaded successfully")
        except ImportError as e:
            logger.error(f"Required libraries not available: {e}")
            raise RuntimeError("onnx-asr library required for ASR processing")
        except Exception as e:
            logger.error(f"Failed to initialize ASR model: {e}")
            raise

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup resources"""
        if self.model:
            del self.model

    def _transcribe_file(self, audio_file: str) -> str:
        """Transcribe a single audio file"""
        try:
            audio_array = self._convert_audio_to_array(audio_file)
            result = self.model.recognize(audio_array)
            return result.strip()

        except Exception as e:
            logger.error(f"Transcription error for {audio_file}: {e}")
            raise

    def _convert_audio_to_array(self, audio_file: str) -> np.ndarray:
        """Convert audio file to 16kHz PCM_16 numpy array"""
        try:
            audio, _ = librosa.load(audio_file, sr=16000, mono=True)
            audio_int16 = (audio * 32767).astype(np.int16)
            return audio_int16
        except Exception as e:
            logger.error(f"Audio conversion error for {audio_file}: {e}")
            raise


# Define Parakeet model variants
PARAKEET_VARIANTS = [
    ASRModelVariant(
        model_id="0.6b_v2",
        name="0.6B v2 [English Only]",
        desc="Parakeet TDT 0.6B v2 model. Very fast, reasonably accurate. Recommended for English audiobooks. Uses ~4GB of RAM.",
        path="nemo-parakeet-tdt-0.6b-v2",
        languages=[("en", "English")],
    ),
    ASRModelVariant(
        model_id="0.6b_v3",
        name="0.6B v3 [Multilingual]",
        desc="Parakeet TDT 0.6B v3 model. Very fast, reasonably accurate. Uses ~4GB of RAM.\nAutomatically detects language. Supported languages: Bulgarian, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French, German, Greek, Hungarian, Italian, Latvian, Lithuanian, Maltese, Polish, Portuguese, Romanian, Slovak, Slovenian, Spanish, Swedish, Russian, Ukrainian.",
        path="nemo-parakeet-tdt-0.6b-v3",
        languages=[("auto", "Auto")],
    ),
]

try:
    import onnx_asr

    # Register Parakeet CPU service
    @register_asr_service(
        service_id="parakeet_cpu",
        name="Parakeet",
        desc="The Parakeet ASR models from NVIDIA.",
        uses_gpu=False,
        variants=PARAKEET_VARIANTS,
        priority=75,
    )
    class ParakeetCPUService(ParakeetASRService):
        """CPU-only Parakeet service"""

        def __init__(
            self, progress_callback: ProgressCallback, model_path: str = "nemo-parakeet-tdt-0.6b-v2", language: str = ""
        ):
            super().__init__(progress_callback, model_path=model_path, language=language)

    logger.info("ASR: ✅ Parakeet CPU service registered")
except ImportError as e:
    logger.error("ASR: ❌ Parakeet CPU service registration failed")
    if "onnxruntime_pybind11_state" in str(e):
        logger.error(
            "Parakeet ASR requires the Microsoft Visual C++ Redistributable. Please install the latest version and restart:"
        )
        logger.error("https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist")
