"""
Whisper.cpp ASR Service Provider

This module provides ASR services using the
whisper.cpp library, with auto-registration.
"""

import asyncio
import logging
import os
import re
import sys
import threading
import tempfile
from typing import List, Tuple

from app.models.enums import Step
from app.models.progress import ProgressCallback
from app.services.asr_service import ASRService
from app.services.asr_service_options import register_asr_service, ASRModelVariant
from pywhispercpp.model import Model

logger = logging.getLogger(__name__)


class ModelDownloadProgress:
    """Captures and publishes whisper.cpp model download progress"""

    def __init__(self, progress_callback):
        self.progress_callback = progress_callback
        self.temp_file = None
        self.monitor_thread = None
        self.stop_monitoring = threading.Event()
        self.last_percent = 0

        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = None

        self.progress_pattern = re.compile(
            r"Downloading Model (\w+(?:\.\w+)?) \.\.\.:\s*(\d+)%\|[█▇▆▅▄▃▂▁▏▎▍▌▋▊▉\s]*\|\s*([\d\.]+[KMGT]?i?B?|0\.00)/([\d\.]+[KMGT]?i?B?)\s+\[([^\]]+)<([^\]<>?]+),?\s*([^\]]+)\]"
        )

    def __enter__(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
        self.monitor_thread = threading.Thread(target=self._monitor_file)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        return self.temp_file

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_monitoring.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)

        if self.temp_file:
            try:
                temp_path = self.temp_file.name
                self.temp_file.close()
                os.unlink(temp_path)
            except (OSError, AttributeError):
                pass

    def _monitor_file(self):
        if not self.temp_file:
            return

        temp_file_path = self.temp_file.name

        try:
            with open(temp_file_path, "r") as f:
                while not self.stop_monitoring.is_set():
                    line = f.readline()
                    if line:
                        self._parse_progress_line(line)
                    else:
                        # No new content, wait a bit
                        self.stop_monitoring.wait(0.1)
        except Exception as e:
            logger.error(f"Error monitoring progress file: {e}")

    def _parse_progress_line(self, line):
        match = self.progress_pattern.search(line)
        if match:
            model_name = match.group(1)
            percent = int(match.group(2))
            downloaded = match.group(3)
            total = match.group(4)

            if percent != self.last_percent:
                self.last_percent = percent
                message = f"Downloading {model_name} model: {downloaded}/{total}"
                try:
                    if self.loop and self.loop.is_running():
                        self.loop.call_soon_threadsafe(
                            self.progress_callback, Step.ASR_PROCESSING, percent, message, {}
                        )
                except Exception as e:
                    logger.error(f"Error in progress callback: {e}")


class WhisperCppASRService(ASRService):
    """ASR service using whisper.cpp"""

    def __init__(
        self,
        progress_callback: ProgressCallback,
        use_gpu: bool = False,
        model_path: str = "tiny",
        language: str = "",
    ):
        super().__init__(progress_callback, model_path, language)
        self.model: Model = None

    @property
    def service_name(self) -> str:
        return "Whisper"

    async def __aenter__(self):
        """Initialize the ASR model"""
        try:
            self._notify_progress(Step.ASR_PROCESSING, 0, "Loading ASR model. This may take a while the first time...")

            model_cache_dir = os.getenv("MODEL_CACHE_DIR", None)

            if model_cache_dir:
                model_cache_dir = os.path.join(model_cache_dir, "whispercpp")

            with ModelDownloadProgress(self._notify_progress) as log_file:

                def create_model():
                    import contextlib

                    with contextlib.redirect_stderr(log_file), contextlib.redirect_stdout(log_file):
                        sys.stdout.flush()
                        sys.stderr.flush()

                        model = Model(self.model_path, models_dir=model_cache_dir, redirect_whispercpp_logs_to=log_file)

                        log_file.flush()
                        return model

                loop = asyncio.get_event_loop()
                self.model = await loop.run_in_executor(None, create_model)

            self._notify_progress(Step.ASR_PROCESSING, 0, "ASR model loaded successfully")

        except Exception as e:
            logger.error(f"Failed to initialize ASR model: {e}")
            raise

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup resources"""
        if hasattr(self, "model") and self.model:
            del self.model

    def _transcribe_file(self, audio_file: str) -> str:
        """Transcribe a single audio file"""

        try:
            results = self.model.transcribe(
                audio_file,
                language=self.language,
                suppress_blank=True,
                initial_prompt=self.bias_words,
            )

            return "".join([result.text for result in results]).strip()

        except Exception as e:
            logger.error(f"Transcription error for {audio_file}: {e}")
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


# Define Whisper model variants
WHISPER_VARIANTS = [
    ASRModelVariant(
        model_id="tiny",
        name="Tiny",
        desc="Tiny version of the Whisper model. Fastest (~10x faster than Large), but least accurate. Uses ~1GB of memory",
        path="tiny",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="tiny_en",
        name="Tiny (EN)",
        desc="[English-only] Tiny version of the Whisper model. Fastest (~10x faster than Large), but least accurate. Generally more accurate for English audio than the standard Tiny version. Uses ~1GB of memory.",
        path="tiny.en",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="base",
        name="Base",
        desc="Base version of the Whisper model. Fast (~7x faster than Large), but less accurate than larger models. Uses ~1GB of memory.",
        path="base",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="base_en",
        name="Base (EN)",
        desc="[English-only] Base version of the Whisper model. Fast (~7x faster than Large), but less accurate than larger models. Generally more accurate for English audio than the standard Base version. Uses ~1GB of memory.",
        path="base.en",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="small",
        name="Small",
        desc="Small version of the Whisper model. Moderate speed (~4x faster than Large), moderate accuracy. Uses ~2GB of memory.",
        path="small",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="small_en",
        name="Small (EN)",
        desc="[English-only] Small version of the Whisper model. Moderate speed (~4x faster than Large), moderate accuracy. A bit more accurate for English audio than the standard Small version. Uses ~2GB of memory.",
        path="small.en",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="medium",
        name="Medium",
        desc="Medium version of the Whisper model. Slower (~2x faster than Large), but reasonably accurate. Uses ~5GB of memory.",
        path="medium",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="medium_en",
        name="Medium (EN)",
        desc="[English-only] Medium version of the Whisper model. Slower (~2x faster than Large), but reasonably accurate. A bit more accurate for English audio than the standard Medium version. Uses ~5GB of memory.",
        path="medium.en",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="large",
        name="Large",
        desc="Largest version of the Whisper model. Slowest, but most accurate. Uses ~10GB of memory.",
        path="large-v3",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="turbo",
        name="Turbo",
        desc="Optimized version of the Large Whisper model. Fast (~8x faster than Large), while remaining reasonably accurate. Uses ~6GB of memory.",
        path="large-v3-turbo",
        languages=WHISPER_LANGS,
    ),
]


# Register Whisper service
@register_asr_service(
    service_id="whisper_cpp",
    name="Whisper",
    desc="The Whisper ASR model by OpenAI.",
    uses_gpu=False,
    supports_bias_words=True,
    variants=WHISPER_VARIANTS,
    priority=80,
)
class WhisperCPUService(WhisperCppASRService):
    """CPU-only Whisper service"""

    def __init__(self, progress_callback: ProgressCallback, model_path: str = "tiny", language: str = ""):
        super().__init__(progress_callback, use_gpu=False, model_path=model_path, language=language)


logger.info("ASR: ✅ Whisper service registered")
