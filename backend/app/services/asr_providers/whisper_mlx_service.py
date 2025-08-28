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


WHISPER_LANGS: List[Tuple[str, str, str]] = [
    ("auto", "Auto", "Auto"),
    ("af", "Afrikaans", "Afrikaans"),
    ("sq", "Albanian", "Shqip"),
    ("am", "Amharic", "አማርኛ"),
    ("ar", "Arabic", "العربية"),
    ("hy", "Armenian", "Հայերեն"),
    ("as", "Assamese", "অসমীয়া"),
    ("az", "Azerbaijani", "Azərbaycanca"),
    ("ba", "Bashkir", "Башҡортса"),
    ("eu", "Basque", "Euskera"),
    ("be", "Belarusian", "Беларуская"),
    ("bn", "Bengali", "বাংলা"),
    ("bs", "Bosnian", "Bosanski"),
    ("br", "Breton", "Brezhoneg"),
    ("bg", "Bulgarian", "Български"),
    ("yue", "Cantonese", "粵語"),
    ("ca", "Catalan", "Català"),
    ("zh", "Chinese", "中文"),
    ("hr", "Croatian", "Hrvatski"),
    ("cs", "Czech", "Čeština"),
    ("da", "Danish", "Dansk"),
    ("nl", "Dutch", "Nederlands"),
    ("en", "English", "English"),
    ("et", "Estonian", "Eesti"),
    ("fo", "Faroese", "Føroyskt"),
    ("fi", "Finnish", "Suomi"),
    ("fr", "French", "Français"),
    ("gl", "Galician", "Galego"),
    ("ka", "Georgian", "ქართული"),
    ("de", "German", "Deutsch"),
    ("el", "Greek", "Ελληνικά"),
    ("gu", "Gujarati", "ગુજરાતી"),
    ("ht", "Haitian creole", "Kreyòl ayisyen"),
    ("ha", "Hausa", "Hausa"),
    ("haw", "Hawaiian", "ʻŌlelo Hawaiʻi"),
    ("he", "Hebrew", "עברית"),
    ("hi", "Hindi", "हिन्दी"),
    ("hu", "Hungarian", "Magyar"),
    ("is", "Icelandic", "Íslenska"),
    ("id", "Indonesian", "Bahasa Indonesia"),
    ("it", "Italian", "Italiano"),
    ("ja", "Japanese", "日本語"),
    ("jw", "Javanese", "Basa Jawa"),
    ("kn", "Kannada", "ಕನ್ನಡ"),
    ("kk", "Kazakh", "Қазақша"),
    ("km", "Khmer", "ខ្មែរ"),
    ("ko", "Korean", "한국어"),
    ("lo", "Lao", "ລາວ"),
    ("la", "Latin", "Latina"),
    ("lv", "Latvian", "Latviešu"),
    ("ln", "Lingala", "Lingála"),
    ("lt", "Lithuanian", "Lietuvių"),
    ("lb", "Luxembourgish", "Lëtzebuergesch"),
    ("mk", "Macedonian", "Македонски"),
    ("mg", "Malagasy", "Malagasy"),
    ("ms", "Malay", "Bahasa Melayu"),
    ("ml", "Malayalam", "മലയാളം"),
    ("mt", "Maltese", "Malti"),
    ("mi", "Maori", "Te Reo Māori"),
    ("mr", "Marathi", "मराठी"),
    ("mn", "Mongolian", "Монгол"),
    ("my", "Myanmar", "မြန်မာ"),
    ("ne", "Nepali", "नेपाली"),
    ("no", "Norwegian", "Norsk"),
    ("nn", "Nynorsk", "Nynorsk"),
    ("oc", "Occitan", "Occitan"),
    ("ps", "Pashto", "پښتو"),
    ("fa", "Persian", "فارسی"),
    ("pl", "Polish", "Polski"),
    ("pt", "Portuguese", "Português"),
    ("pa", "Punjabi", "ਪੰਜਾਬੀ"),
    ("ro", "Romanian", "Română"),
    ("ru", "Russian", "Русский"),
    ("sa", "Sanskrit", "संस्कृतम्"),
    ("sr", "Serbian", "Српски"),
    ("sn", "Shona", "ChiShona"),
    ("sd", "Sindhi", "سنڌي"),
    ("si", "Sinhala", "සිංහල"),
    ("sk", "Slovak", "Slovenčina"),
    ("sl", "Slovenian", "Slovenščina"),
    ("so", "Somali", "Soomaali"),
    ("es", "Spanish", "Español"),
    ("su", "Sundanese", "Basa Sunda"),
    ("sw", "Swahili", "Kiswahili"),
    ("sv", "Swedish", "Svenska"),
    ("tl", "Tagalog", "Tagalog"),
    ("tg", "Tajik", "Тоҷикӣ"),
    ("ta", "Tamil", "தமிழ்"),
    ("tt", "Tatar", "Татарча"),
    ("te", "Telugu", "తెలుగు"),
    ("th", "Thai", "ไทย"),
    ("bo", "Tibetan", "བོད་ཡིག"),
    ("tr", "Turkish", "Türkçe"),
    ("tk", "Turkmen", "Türkmençe"),
    ("uk", "Ukrainian", "Українська"),
    ("ur", "Urdu", "اردو"),
    ("uz", "Uzbek", "Oʻzbekcha"),
    ("vi", "Vietnamese", "Tiếng Việt"),
    ("cy", "Welsh", "Cymraeg"),
    ("yi", "Yiddish", "ייִדיש"),
    ("yo", "Yoruba", "Yorùbá"),
]

EN_LANG: List[Tuple[str, str, str]] = [("en", "English", "English")]

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
