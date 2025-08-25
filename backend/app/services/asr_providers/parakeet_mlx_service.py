"""
Parakeet MLX ASR Service Provider

This module provides the Parakeet MLX ASR service for Apple Silicon acceleration,
with auto-registration.
"""

import logging
import sys

from app.models.enums import Step
from app.models.progress import ProgressCallback
from app.services.asr_service import ASRService
from app.services.asr_service_options import register_asr_service, ASRModelVariant

logger = logging.getLogger(__name__)


class ParakeetMLXASRService(ASRService):
    """ASR service using Parakeet MLX for macOS acceleration"""

    def __init__(
        self,
        progress_callback: ProgressCallback,
        model_path: str = "mlx-community/parakeet-tdt-0.6b-v2",
        language: str = "",
    ):
        super().__init__(progress_callback, model_path, language)
        self.model = None

    @property
    def service_name(self) -> str:
        return "Parakeet MLX"

    async def __aenter__(self):
        """Initialize Parakeet MLX ASR"""
        try:
            import parakeet_mlx

            self.parakeet_mlx = parakeet_mlx
            self._notify_progress(
                Step.ASR_PROCESSING, 0, f"Loading Parakeet MLX model {self.model_path}. This may take a while..."
            )
            self.model = parakeet_mlx.from_pretrained(self.model_path)
            self._notify_progress(Step.ASR_PROCESSING, 0, "Parakeet MLX ASR ready")

        except ImportError as e:
            logger.error(f"Parakeet MLX not available: {e}")
            raise RuntimeError("Parakeet MLX required for macOS ASR processing")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.model = None
        pass

    def _transcribe_file(self, audio_file: str) -> str:
        """Transcribe a single audio file using Parakeet MLX"""
        try:
            result = self.model.transcribe(audio_file)
            return result.text.strip()

        except Exception as e:
            logger.error(f"Parakeet MLX transcription error for {audio_file}: {e}")
            raise


# Define Parakeet MLX model variants
PARAKEET_MLX_VARIANTS = [
    ASRModelVariant(
        model_id="0.6b_v2",
        name="0.6B v2 [English Only]",
        desc="Parakeet TDT 0.6B v2 model. Very fast, reasonably accurate. Recommended for English audiobooks. Uses ~4GB of VRAM.",
        path="mlx-community/parakeet-tdt-0.6b-v2",
        languages=[("en", "English")],
    ),
    ASRModelVariant(
        model_id="0.6b_v3",
        name="0.6B v3 [Multilingual]",
        desc="Parakeet TDT 0.6B v3 model. Very fast, reasonably accurate. Uses ~4GB of VRAM.\nAutomatically detects language. Supported languages: Bulgarian, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French, German, Greek, Hungarian, Italian, Latvian, Lithuanian, Maltese, Polish, Portuguese, Romanian, Slovak, Slovenian, Spanish, Swedish, Russian, Ukrainian.",
        path="mlx-community/parakeet-tdt-0.6b-v3",
        languages=[("auto", "Auto")],
    ),
]

# Register Parakeet MLX service (only on macOS with Parakeet MLX available)
if sys.platform == "darwin":
    try:
        import parakeet_mlx

        @register_asr_service(
            service_id="parakeet_mlx",
            name="Parakeet MLX",
            desc="The Parakeet ASR models by NVIDIA, optimized for Apple Silicon (MLX).",
            uses_gpu=True,
            variants=PARAKEET_MLX_VARIANTS,
            priority=90,
        )
        class ParakeetMLXService(ParakeetMLXASRService):
            """MLX-accelerated Parakeet service for Apple Silicon"""

            pass

        logger.info("ASR: ✅ Parakeet MLX service registered")
    except ImportError:
        logger.info("ASR: ✖️ Parakeet MLX not registered (parakeet_mlx not available)")
else:
    logger.info("ASR: ✖️ Parakeet MLX not registered (current platform is not macOS)")
