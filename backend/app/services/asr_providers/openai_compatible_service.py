"""
OpenAI-Compatible Transcription API Provider

Sends chapter snippets to any server implementing OpenAI's ``POST /audio/transcriptions``:
self-hosted ones (Speaches, whisper.cpp's server, LocalAI, vLLM, ...) or cloud services
(OpenAI, Groq, ...). The model can be anything the server offers, Whisper or not.
"""

import io
import logging
import os
import random
import re
import subprocess
import time
import wave
from dataclasses import astuple, dataclass
from typing import Any, Dict, List, NoReturn, Optional
from urllib.parse import urlparse

import httpx

from app.core.ffmpeg import ffmpeg_path
from app.models.progress import ProgressCallback
from app.services.asr_providers.whisper_cpp_service import WHISPER_LANGS
from app.services.asr_service import ASRFatalError, ASRService
from app.services.asr_service_options import ASRModelVariant, register_asr_service

logger = logging.getLogger(__name__)

SERVICE_ID = "openai_compatible"

TRANSCRIPTIONS_PATH = "/audio/transcriptions"

# Snippets are uploaded as 16 kHz mono 16-bit WAV: every server reads WAV (whisper.cpp's
# server rejects AAC/M4A outright), and Whisper and Parakeet resample to 16 kHz anyway
SAMPLE_RATE = 16000

# Bounds for HostedASRConfig.parallel_requests
MAX_PARALLEL_REQUESTS = 16

CONNECT_TIMEOUT = 10.0

# Generous, since a self-hosted server may load the model on its first request
# (Speaches took 25 s to load Parakeet on CPU)
READ_TIMEOUT = 300.0

# Retries per request after a rate limit, server error or dropped connection,
# starting at RETRY_BASE_DELAY seconds and doubling (a Retry-After header takes precedence)
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

# A Retry-After longer than this fails the request instead of stalling the batch
MAX_RETRY_AFTER = 60.0

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

# Model ids that look like transcription models; /models on a cloud API also lists chat,
# embedding and TTS models, which the model picker leaves out
_ASR_MODEL_PATTERN = re.compile(r"whisper|transcri|parakeet|canary|voxtral|asr|stt", re.IGNORECASE)


@dataclass(frozen=True)
class HostedSettings:
    base_url: str
    api_key: str
    model: str
    skip_ssl_verify: bool
    parallel_requests: int


def normalize_base_url(url: str) -> str:
    """Add a missing scheme and drop a trailing slash, or the endpoint path if the full
    transcription URL was pasted."""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    url = url.rstrip("/")
    if url.endswith(TRANSCRIPTIONS_PATH):
        url = url[: -len(TRANSCRIPTIONS_PATH)]
    return url


def load_settings() -> HostedSettings:
    from app.core.config import get_app_config

    config = get_app_config().hosted_asr
    return HostedSettings(
        base_url=normalize_base_url(config.base_url),
        api_key=config.api_key.strip(),
        model=config.model.strip(),
        skip_ssl_verify=config.skip_ssl_verify,
        parallel_requests=min(max(int(config.parallel_requests), 1), MAX_PARALLEL_REQUESTS),
    )


def _headers(settings: HostedSettings) -> Dict[str, str]:
    return {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)


def encode_wav(audio_file: str) -> bytes:
    """Decode audio_file to 16 kHz mono WAV in memory"""
    process = subprocess.run(
        [ffmpeg_path(), "-nostdin", "-loglevel", "error", "-i", audio_file, "-map", "0:a:0"]
        + ["-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        capture_output=True,
        check=True,
    )
    return pcm_to_wav(process.stdout)


def pcm_to_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return buffer.getvalue()


def request_fields(settings: HostedSettings, language: str, prompt: str) -> Dict[str, str]:
    """Form fields for a transcription request. Only fields that are set are sent: servers
    with a single model ignore or lack `model`, and OpenAI rejects language "auto"."""
    fields = {"response_format": "json"}
    if settings.model:
        fields["model"] = settings.model
    if language and language != "auto":
        fields["language"] = language
    if prompt:
        fields["prompt"] = prompt
    return fields


def _validation_error(error: Any) -> str:
    if not isinstance(error, dict):
        return str(error)
    # loc is like ["body", "model"]: drop the request part it came from
    loc = [str(part) for part in error.get("loc", []) if part not in ("body", "query", "header")]
    message = str(error.get("msg", error))
    return f"{'.'.join(loc)}: {message}" if loc else message


def error_detail(response: httpx.Response) -> str:
    """The server's own error message: OpenAI's {"error": {"message"}}, FastAPI's
    {"detail"}, or the body as text"""
    try:
        data = response.json()
    except ValueError:
        data = None

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str) and error:
            return error
        detail = data.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        if isinstance(detail, list) and detail:
            # FastAPI validation errors, e.g. Speaches without a model: "model: Field required"
            return "; ".join(_validation_error(d) for d in detail)
        if data.get("message"):
            return str(data["message"])

    text = response.text.strip()
    return text[:300] if text else (response.reason_phrase or "no details")


def status_error_message(response: httpx.Response) -> str:
    detail = error_detail(response)
    code = response.status_code
    if code in (401, 403):
        return f"The server rejected the API key (HTTP {code}): {detail}"
    if code == 404:
        return (
            f"Not found (HTTP 404): {detail}. Check the server URL (it usually ends in /v1) "
            "and that the model name is one the server has."
        )
    if code == 429:
        return f"Rate limited by the server (HTTP 429): {detail}. Try fewer parallel requests."
    return f"The server returned an error (HTTP {code}): {detail}"


def transport_error_message(settings: HostedSettings, error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.ConnectTimeout):
        message = f"Timed out connecting to {settings.base_url}"
    elif isinstance(error, httpx.TimeoutException):
        return f"The server didn't respond within {READ_TIMEOUT:.0f} seconds"
    elif isinstance(error, httpx.ConnectError):
        message = f"Couldn't connect to {settings.base_url}: {error}"
        if "CERTIFICATE_VERIFY_FAILED" in str(error):
            return f"{message}. If the server uses a self-signed certificate, enable Skip SSL certificate verification."
    elif isinstance(error, httpx.UnsupportedProtocol):
        return f"Invalid server URL {settings.base_url}: {error}"
    else:
        return f"Connection to {settings.base_url} failed: {error}"

    host = urlparse(settings.base_url).hostname or ""
    if os.environ.get("ACHEW_DOCKER") and host in ("localhost", "127.0.0.1", "::1"):
        message += (
            ". Achew is running in Docker, where localhost is the container itself: "
            "use the host's IP address or host.docker.internal instead"
        )
    return message


def parse_transcript(response: httpx.Response) -> str:
    """The transcript from a successful response: JSON {"text": ...}, or plain text from
    servers that ignore response_format"""
    try:
        data = response.json()
    except ValueError:
        return response.text
    if isinstance(data, dict):
        if isinstance(data.get("text"), str):
            return data["text"]
        raise ValueError(f"Unexpected response from the server: {response.text[:300]}")
    return response.text


def _retry_delay(attempt: int, response: Optional[httpx.Response] = None) -> float:
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
    return RETRY_BASE_DELAY * (2**attempt) * random.uniform(0.8, 1.2)


def filter_transcription_models(data: Any) -> List[str]:
    """Model ids from a /models response, narrowed to transcription models when it says
    which those are (Speaches' `task`) or when any id looks like one"""
    entries = data.get("data") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return []
    models = [e for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)]

    if any("task" in m for m in models):
        models = [m for m in models if m.get("task") == "automatic-speech-recognition"]
    elif any(_ASR_MODEL_PATTERN.search(m["id"]) for m in models):
        models = [m for m in models if _ASR_MODEL_PATTERN.search(m["id"])]

    return sorted({m["id"] for m in models}, key=str.lower)


class HostedASRError(Exception):
    """A request to the configured server failed; the message says why"""


async def list_models(settings: HostedSettings) -> List[str]:
    """Transcription models the server lists. Raises HostedASRError when it can't be
    reached; a server without /models (whisper.cpp's) returns an empty list."""
    if not settings.base_url:
        raise HostedASRError("No server URL is set")
    try:
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT, verify=not settings.skip_ssl_verify) as client:
            response = await client.get(f"{settings.base_url}/models", headers=_headers(settings))
    except httpx.HTTPError as e:
        raise HostedASRError(transport_error_message(settings, e)) from e

    if response.status_code in (401, 403):
        raise HostedASRError(status_error_message(response))
    if response.is_error:
        return []
    try:
        return filter_transcription_models(response.json())
    except ValueError:
        return []


async def test_transcription(settings: HostedSettings, language: str, prompt: str) -> float:
    """Transcribe one second of silence with the configured settings and return how long
    it took. Raises HostedASRError with the reason when it fails."""
    if not settings.base_url:
        raise HostedASRError("No server URL is set")
    silence = pcm_to_wav(b"\x00\x00" * SAMPLE_RATE)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_timeout(), verify=not settings.skip_ssl_verify) as client:
            response = await client.post(
                f"{settings.base_url}{TRANSCRIPTIONS_PATH}",
                headers=_headers(settings),
                data=request_fields(settings, language, prompt),
                files={"file": ("test.wav", silence, "audio/wav")},
            )
    except httpx.HTTPError as e:
        raise HostedASRError(transport_error_message(settings, e)) from e

    if response.is_error:
        raise HostedASRError(status_error_message(response))
    try:
        parse_transcript(response)
    except ValueError as e:
        raise HostedASRError(str(e)) from e
    return time.monotonic() - started


OPENAI_COMPATIBLE_VARIANTS = [
    # A single entry carrying the language list; the model is whatever the server offers
    ASRModelVariant(model_id="api", name="API", desc="", path="", languages=WHISPER_LANGS),
]


@register_asr_service(
    service_id=SERVICE_ID,
    name="OpenAI-Compatible API",
    desc="Sends audio to a transcription server with an OpenAI-compatible API, such as a self-hosted "
    "Speaches, whisper.cpp or LocalAI server, or a cloud service like OpenAI or Groq.",
    supports_bias_words=True,
    variants=OPENAI_COMPATIBLE_VARIANTS,
    priority=10,
    asr_buffer=0.1,
    hosted=True,
)
class OpenAICompatibleASRService(ASRService):
    """ASR service that sends audio to an OpenAI-compatible transcription endpoint"""

    def __init__(self, progress_callback: ProgressCallback, model_path: str = "", language: str = ""):
        super().__init__(progress_callback, model_path, language)
        self.settings = load_settings()
        self.parallel_requests = self.settings.parallel_requests
        self._client: Optional[httpx.Client] = None
        # Until one request has worked, any failure is taken to be a configuration problem
        # and stops the batch; after that, only an unreachable server or a rejected key does
        self._succeeded = False

    @classmethod
    def config_key(cls) -> tuple:
        return astuple(load_settings())

    @property
    def service_name(self) -> str:
        return "OpenAI-compatible API"

    async def __aenter__(self):
        if not self.settings.base_url:
            raise ASRFatalError(
                "No server URL is set for the OpenAI-compatible API. Set one in Transcription Settings."
            )
        self._client = httpx.Client(
            base_url=self.settings.base_url,
            headers=_headers(self.settings),
            timeout=_timeout(),
            verify=not self.settings.skip_ssl_verify,
            limits=httpx.Limits(
                max_connections=self.parallel_requests, max_keepalive_connections=self.parallel_requests
            ),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client is not None:
            self._client.close()
            self._client = None

    def _fail(self, message: str) -> NoReturn:
        if not self._succeeded:
            raise ASRFatalError(message)
        raise RuntimeError(message)

    def _post(self, wav: bytes) -> httpx.Response:
        """POST the snippet, retrying rate limits, server errors and dropped connections"""
        if self._client is None:
            raise RuntimeError("OpenAI-compatible ASR service is not open")
        fields = request_fields(self.settings, self.language, self.bias_words)
        attempt = 0
        while True:
            try:
                response = self._client.post(
                    TRANSCRIPTIONS_PATH, data=fields, files={"file": ("audio.wav", wav, "audio/wav")}
                )
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # Fail fast on a wrong URL; retry a server that was answering a moment ago
                if not self._succeeded or attempt >= MAX_RETRIES:
                    raise
                delay = _retry_delay(attempt)
            except (httpx.NetworkError, httpx.RemoteProtocolError):
                # Also covers a kept-alive connection the server closed while idle
                if attempt >= MAX_RETRIES:
                    raise
                delay = _retry_delay(attempt)
            else:
                if response.status_code not in RETRYABLE_STATUS or attempt >= MAX_RETRIES:
                    return response
                delay = _retry_delay(attempt, response)
                if delay > MAX_RETRY_AFTER:
                    return response
                logger.info(f"Transcription server returned HTTP {response.status_code}; retrying in {delay:.1f}s")

            attempt += 1
            time.sleep(delay)

    def _transcribe_file(self, audio_file: str, retry_on_empty: bool = True) -> str:
        wav = encode_wav(audio_file)
        if len(wav) <= 44:  # header only: nothing to transcribe
            return ""

        try:
            response = self._post(wav)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.UnsupportedProtocol) as e:
            raise ASRFatalError(transport_error_message(self.settings, e)) from e
        except httpx.HTTPError as e:
            self._fail(transport_error_message(self.settings, e))

        if response.status_code in (401, 403):
            raise ASRFatalError(status_error_message(response))
        if response.is_error:
            self._fail(status_error_message(response))

        try:
            text = parse_transcript(response)
        except ValueError as e:
            self._fail(str(e))

        self._succeeded = True
        return text.strip()


logger.info("ASR: ✅ OpenAI-compatible API service registered")
