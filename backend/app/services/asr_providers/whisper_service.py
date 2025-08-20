"""
Whisper ASR Service Provider

This module provides CPU and GPU-based Whisper ASR services using the
Transformers library, with auto-registration.
"""

import logging
from typing import List, Tuple

from app.models.enums import Step
from app.models.progress import ProgressCallback
from app.services.asr_service import ASRService
from app.services.asr_service_options import register_asr_service, ASRModelVariant

logger = logging.getLogger(__name__)


class WhisperASRService(ASRService):
    """ASR service using Whisper via the Transformers library"""

    def __init__(
        self,
        progress_callback: ProgressCallback,
        use_gpu: bool = False,
        model_path: str = "openai/whisper-tiny",
        language: str = "",
    ):
        super().__init__(progress_callback, model_path, language)
        self.model = None
        self.processor = None
        self.use_gpu = use_gpu

    @property
    def service_name(self) -> str:
        return "Transformers"

    async def __aenter__(self):
        """Initialize the ASR model"""
        try:
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
            import torch

            self._notify_progress(Step.ASR_PROCESSING, 0, "Loading ASR model...")

            if torch.cuda.is_available():
                device = "cuda:0"
                torch_dtype = torch.float16
            else:
                device = "cpu"
                torch_dtype = torch.float32

            # Load model
            self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
                self.model_path,
                torch_dtype=torch_dtype,
                low_cpu_mem_usage=True,
                use_safetensors=True,
            )
            self.model.to(device)

            # Load processor
            self.processor = AutoProcessor.from_pretrained(self.model_path)

            # Create pipeline with language parameter if specified
            pipeline_kwargs = {
                "model": self.model,
                "tokenizer": self.processor.tokenizer,
                "feature_extractor": self.processor.feature_extractor,
                "max_new_tokens": 128,
                "chunk_length_s": 30,
                "batch_size": 16,
                "return_timestamps": True,
                "torch_dtype": torch_dtype,
                "device": device,
            }

            # Add language parameter if specified and not "auto"
            # Note: English-only models (ending in .en) don't accept language parameters
            is_english_only = self.model_path.endswith(".en")
            if self.language and self.language != "auto" and not is_english_only:
                pipeline_kwargs["generate_kwargs"] = {"language": self.language}

            self.pipe = pipeline("automatic-speech-recognition", **pipeline_kwargs)

            self._notify_progress(Step.ASR_PROCESSING, 0, "ASR model loaded successfully")

        except ImportError as e:
            logger.error(f"Required libraries not available: {e}")
            raise RuntimeError("Transformers library required for ASR processing")
        except Exception as e:
            logger.error(f"Failed to initialize ASR model: {e}")
            raise

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup resources"""
        if hasattr(self, "model") and self.model:
            del self.model
        if hasattr(self, "processor") and self.processor:
            del self.processor
        if hasattr(self, "pipe") and self.pipe:
            del self.pipe

    def _transcribe_file(self, audio_file: str) -> str:
        """Transcribe a single audio file"""
        if not self.pipe:
            raise RuntimeError("ASR model not initialized")

        try:
            result = self.pipe(audio_file)

            if isinstance(result, dict) and "text" in result:
                return result["text"].strip()
            elif isinstance(result, str):
                return result.strip()
            else:
                logger.warning(f"Unexpected transcription result format: {type(result)}")
                return str(result).strip()

        except Exception as e:
            logger.error(f"Transcription error for {audio_file}: {e}")
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


# Define Whisper model variants
WHISPER_VARIANTS = [
    ASRModelVariant(
        model_id="tiny",
        name="Tiny",
        desc="Tiny version of the Whisper model. Fastest (~10x faster than Large), but least accurate. Uses ~1GB of memory",
        path="openai/whisper-tiny",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="tiny_en",
        name="Tiny (EN)",
        desc="[English-only] Tiny version of the Whisper model. Fastest (~10x faster than Large), but least accurate. Generally more accurate for English audio than the standard Tiny version. Uses ~1GB of memory.",
        path="openai/whisper-tiny.en",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="base",
        name="Base",
        desc="Base version of the Whisper model. Fast (~7x faster than Large), but less accurate than larger models. Uses ~1GB of memory.",
        path="openai/whisper-base",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="base_en",
        name="Base (EN)",
        desc="[English-only] Base version of the Whisper model. Fast (~7x faster than Large), but less accurate than larger models. Generally more accurate for English audio than the standard Base version. Uses ~1GB of memory.",
        path="openai/whisper-base.en",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="small",
        name="Small",
        desc="Small version of the Whisper model. Moderate speed (~4x faster than Large), moderate accuracy. Uses ~2GB of memory.",
        path="openai/whisper-small",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="small_en",
        name="Small (EN)",
        desc="[English-only] Small version of the Whisper model. Moderate speed (~4x faster than Large), moderate accuracy. A bit more accurate for English audio than the standard Small version. Uses ~2GB of memory.",
        path="openai/whisper-small.en",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="medium",
        name="Medium",
        desc="Medium version of the Whisper model. Slower (~2x faster than Large), but reasonably accurate. Uses ~5GB of memory.",
        path="openai/whisper-medium",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="medium_en",
        name="Medium (EN)",
        desc="[English-only] Medium version of the Whisper model. Slower (~2x faster than Large), but reasonably accurate. A bit more accurate for English audio than the standard Medium version. Uses ~5GB of memory.",
        path="openai/whisper-medium.en",
        languages=EN_LANG,
    ),
    ASRModelVariant(
        model_id="large",
        name="Large",
        desc="Largest version of the Whisper model. Slowest, but most accurate. Uses ~10GB of memory.",
        path="openai/whisper-large-v3",
        languages=WHISPER_LANGS,
    ),
    ASRModelVariant(
        model_id="turbo",
        name="Turbo",
        desc="Optimized version of the Large Whisper model. Fast (~8x faster than Large), while remaining reasonably accurate. Uses ~6GB of memory.",
        path="openai/whisper-large-v3-turbo",
        languages=WHISPER_LANGS,
    ),
]


# Register Whisper CPU service
@register_asr_service(
    service_id="whisper_cpu",
    name="Whisper",
    desc="The Whisper ASR model by OpenAI.",
    uses_gpu=False,
    variants=WHISPER_VARIANTS,
    priority=70,
)
class WhisperCPUService(WhisperASRService):
    """CPU-only Whisper service"""

    def __init__(
        self, progress_callback: ProgressCallback, model_path: str = "openai/whisper-tiny", language: str = ""
    ):
        super().__init__(progress_callback, use_gpu=False, model_path=model_path, language=language)


logger.info("ASR: ✅ Whisper CPU service registered")
