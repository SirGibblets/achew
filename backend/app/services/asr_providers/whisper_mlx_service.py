"""
Whisper MLX ASR Service Provider

This module provides the Whisper MLX ASR service for Apple Silicon acceleration,
with auto-registration.
"""

import logging
import sys
from typing import List, Tuple

from app.models.enums import Step
from app.models.progress import ProgressCallback
from app.services.asr_service import ASRService
from app.services.asr_service_options import register_asr_service, ASRModelVariant

logger = logging.getLogger(__name__)


class WhisperMLXASRService(ASRService):
    """ASR service using Whisper MLX for macOS acceleration"""

    def __init__(
        self,
        progress_callback: ProgressCallback,
        model_path: str = "mlx-community/whisper-tiny",
        language: str = "",
    ):
        super().__init__(progress_callback, model_path, language)
        self.model = None

    @property
    def service_name(self) -> str:
        return "Whisper MLX"

    async def __aenter__(self):
        """Initialize Whisper MLX ASR"""
        try:
            import mlx_whisper

            self.mlx_whisper = mlx_whisper

            logger.info(f"Initializing Whisper MLX ASR with model '{self.model_path}'")
            self._notify_progress(Step.ASR_PROCESSING, 0, "Loading Whisper MLX model. This may take a while...")

            mlx_whisper.load_models.load_model(self.model_path)

            logger.info("Whisper MLX model loaded successfully")
            self._notify_progress(Step.ASR_PROCESSING, 0, "Whisper MLX ASR ready")

        except ImportError as e:
            logger.error(f"Whisper MLX not available: {e}")
            raise RuntimeError("Whisper MLX required for macOS ASR processing")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup resources"""
        pass

    def _transcribe_file(self, audio_file: str) -> str:
        """Transcribe a single audio file using Whisper MLX"""
        try:
            # Build transcription arguments
            transcribe_kwargs = {}

            # Add language parameter if specified and not "auto"
            if self.language and self.language != "auto":
                transcribe_kwargs["language"] = self.language

            result = self.mlx_whisper.transcribe(
                audio_file,
                initial_prompt=self.bias_words,
                **transcribe_kwargs,
            )

            if isinstance(result, dict) and "text" in result:
                return result["text"].strip()
            elif hasattr(result, "text"):
                return result.text.strip()
            else:
                return str(result).strip()

        except Exception as e:
            logger.error(f"MLX transcription error for {audio_file}: {e}")
            raise


WHISPER_LANGS: List[Tuple[str, str]] = [
    ("auto", "Auto"),
    ("af", "Afrikaans"),
    ("sq", "Albanian"),
    ("am", "Amharic"),
    ("ar", "Arabic"),
    ("hy", "Armenian"),
    ("as", "Assamese"),
    ("az", "Azerbaijani"),
    ("ba", "Bashkir"),
    ("eu", "Basque"),
    ("be", "Belarusian"),
    ("bn", "Bengali"),
    ("bs", "Bosnian"),
    ("br", "Breton"),
    ("bg", "Bulgarian"),
    ("yue", "Cantonese"),
    ("ca", "Catalan"),
    ("zh", "Chinese"),
    ("hr", "Croatian"),
    ("cs", "Czech"),
    ("da", "Danish"),
    ("nl", "Dutch"),
    ("en", "English"),
    ("et", "Estonian"),
    ("fo", "Faroese"),
    ("fi", "Finnish"),
    ("fr", "French"),
    ("gl", "Galician"),
    ("ka", "Georgian"),
    ("de", "German"),
    ("el", "Greek"),
    ("gu", "Gujarati"),
    ("ht", "Haitian creole"),
    ("ha", "Hausa"),
    ("haw", "Hawaiian"),
    ("he", "Hebrew"),
    ("hi", "Hindi"),
    ("hu", "Hungarian"),
    ("is", "Icelandic"),
    ("id", "Indonesian"),
    ("it", "Italian"),
    ("ja", "Japanese"),
    ("jw", "Javanese"),
    ("kn", "Kannada"),
    ("kk", "Kazakh"),
    ("km", "Khmer"),
    ("ko", "Korean"),
    ("lo", "Lao"),
    ("la", "Latin"),
    ("lv", "Latvian"),
    ("ln", "Lingala"),
    ("lt", "Lithuanian"),
    ("lb", "Luxembourgish"),
    ("mk", "Macedonian"),
    ("mg", "Malagasy"),
    ("ms", "Malay"),
    ("ml", "Malayalam"),
    ("mt", "Maltese"),
    ("mi", "Maori"),
    ("mr", "Marathi"),
    ("mn", "Mongolian"),
    ("my", "Myanmar"),
    ("ne", "Nepali"),
    ("no", "Norwegian"),
    ("nn", "Nynorsk"),
    ("oc", "Occitan"),
    ("ps", "Pashto"),
    ("fa", "Persian"),
    ("pl", "Polish"),
    ("pt", "Portuguese"),
    ("pa", "Punjabi"),
    ("ro", "Romanian"),
    ("ru", "Russian"),
    ("sa", "Sanskrit"),
    ("sr", "Serbian"),
    ("sn", "Shona"),
    ("sd", "Sindhi"),
    ("si", "Sinhala"),
    ("sk", "Slovak"),
    ("sl", "Slovenian"),
    ("so", "Somali"),
    ("es", "Spanish"),
    ("su", "Sundanese"),
    ("sw", "Swahili"),
    ("sv", "Swedish"),
    ("tl", "Tagalog"),
    ("tg", "Tajik"),
    ("ta", "Tamil"),
    ("tt", "Tatar"),
    ("te", "Telugu"),
    ("th", "Thai"),
    ("bo", "Tibetan"),
    ("tr", "Turkish"),
    ("tk", "Turkmen"),
    ("uk", "Ukrainian"),
    ("ur", "Urdu"),
    ("uz", "Uzbek"),
    ("vi", "Vietnamese"),
    ("cy", "Welsh"),
    ("yi", "Yiddish"),
    ("yo", "Yoruba"),
]

EN_LANG: List[Tuple[str, str]] = [("en", "English")]

# Define MLX Whisper model variants
MLX_WHISPER_VARIANTS = [
    ASRModelVariant(
        model_id="tiny",
        name="Tiny",
        desc="Tiny version of the Whisper model. Fastest (~10x faster than Large), but least accurate. Uses ~1GB of VRAM",
        path="mlx-community/whisper-tiny",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="tiny_en",
        name="Tiny (EN)",
        desc="[English-only] Tiny version of the Whisper model. Fastest (~10x faster than Large), but least accurate. Generally more accurate for English audio than the standard Tiny version. Uses ~1GB of VRAM.",
        path="mlx-community/whisper-tiny.en-mlx",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="base",
        name="Base",
        desc="Base version of the Whisper model. Fast (~7x faster than Large), but less accurate than larger models. Uses ~1GB of VRAM.",
        path="mlx-community/whisper-base-mlx",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="base_en",
        name="Base (EN)",
        desc="[English-only] Base version of the Whisper model. Fast (~7x faster than Large), but less accurate than larger models. Generally more accurate for English audio than the standard Base version. Uses ~1GB of VRAM.",
        path="mlx-community/whisper-base.en-mlx",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="small",
        name="Small",
        desc="Small version of the Whisper model. Moderate speed (~4x faster than Large), moderate accuracy. Uses ~2GB of VRAM.",
        path="mlx-community/whisper-small-mlx",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="small_en",
        name="Small (EN)",
        desc="[English-only] Small version of the Whisper model. Moderate speed (~4x faster than Large), moderate accuracy. A bit more accurate for English audio than the standard Small version. Uses ~2GB of VRAM.",
        path="mlx-community/whisper-small.en-mlx",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="medium",
        name="Medium",
        desc="Medium version of the Whisper model. Slower (~2x faster than Large), but reasonably accurate. Uses ~5GB of VRAM.",
        path="mlx-community/whisper-medium-mlx",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="medium_en",
        name="Medium (EN)",
        desc="[English-only] Medium version of the Whisper model. Slower (~2x faster than Large), but reasonably accurate. A bit more accurate for English audio than the standard Medium version. Uses ~5GB of VRAM.",
        path="mlx-community/whisper-medium.en-mlx",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="large",
        name="Large",
        desc="Largest version of the Whisper model. Slowest, but most accurate. Uses ~10GB of VRAM.",
        path="mlx-community/whisper-large-v3-mlx",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="turbo",
        name="Turbo",
        desc="Optimized version of the Large Whisper model. Fast (~4x faster than Large), while remaining reasonably accurate. Uses ~6GB of VRAM.",
        path="mlx-community/whisper-large-v3-turbo",
        languages=WHISPER_LANGS,
    ),
]

# Register Whisper MLX service (only on macOS with MLX available)
if sys.platform == "darwin":
    try:
        import mlx_whisper

        @register_asr_service(
            service_id="whisper_mlx",
            name="Whisper MLX",
            desc="The Whisper ASR model by OpenAI, optimized for Apple Silicon (MLX).",
            uses_gpu=True,
            supports_bias_words=True,
            variants=MLX_WHISPER_VARIANTS,
            priority=100,
        )
        class WhisperMLXService(WhisperMLXASRService):
            """MLX-accelerated Whisper service for Apple Silicon"""

            def __init__(
                self,
                progress_callback: ProgressCallback,
                model_path: str = "mlx-community/whisper-tiny",
                language: str = "",
            ):
                super().__init__(progress_callback, model_path=model_path, language=language)

        logger.info("ASR: ✅ Whisper MLX service registered")
    except ImportError:
        logger.info("ASR: ✖️ Whisper MLX not registered (mlx_whisper not available)")
else:
    logger.info("ASR: ✖️ Whisper MLX not registered (current platform is not macOS)")
