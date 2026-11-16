"""Tests for the OpenAI-compatible transcription service
(app/services/asr_providers/openai_compatible_service.py) and its settings routes.

The HTTP side runs against pytest-httpx mocks. The behaviours pinned here were each seen on a
real server: whisper.cpp's server rejects M4A uploads (so snippets go up as 16 kHz WAV) and
has no /models; Speaches answers an unknown model with 404 {"detail": ...} and tags its
models with a `task`; cloud APIs rate limit with 429 + Retry-After.
"""

import io
import math
import re
import struct
import subprocess
import threading
import wave
from email.parser import BytesParser
from email.policy import default as default_policy
from time import sleep as real_sleep

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import config as config_routes
from app.core import config as C
from app.core.ffmpeg import ffmpeg_path
from app.services import asr_service_options
from app.services.asr_providers import openai_compatible_service as hosted
from app.services.asr_providers.openai_compatible_service import (
    HostedASRError,
    OpenAICompatibleASRService,
    filter_transcription_models,
    normalize_base_url,
    request_fields,
)
from app.services.asr_service import ASRFatalError, ASRService

BASE_URL = "http://asr.test/v1"
ENDPOINT = f"{BASE_URL}/audio/transcriptions"


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    """An in-memory config pointing at the mocked server; saving never touches disk"""
    app_cfg = C.AppConfig()
    app_cfg.hosted_asr.base_url = BASE_URL
    app_cfg.user_preferences.preferred_asr_service = hosted.SERVICE_ID
    app_cfg.user_preferences.preferred_asr_language = "en"
    monkeypatch.setattr(C, "_app_config", app_cfg)
    monkeypatch.setattr(C, "save_config", lambda config: True)
    return app_cfg


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch):
    """Record retry delays instead of sleeping them (this patches the time module itself,
    hence real_sleep where a test needs a delay)"""
    delays = []
    monkeypatch.setattr(hosted.time, "sleep", delays.append)
    return delays


def make_audio(path, seconds: float = 1.0, frequency: int = 440) -> str:
    """An AAC tone, like the stream-copied segments transcription gets (the bundled ffmpeg
    has no lavfi to synthesize one)"""
    rate = 22050
    samples = (int(12000 * math.sin(2 * math.pi * frequency * n / rate)) for n in range(int(seconds * rate)))
    wav_path = path.with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    subprocess.run(
        [ffmpeg_path(), "-y", "-loglevel", "error", "-i", str(wav_path), "-c:a", "aac", str(path)], check=True
    )
    return str(path)


@pytest.fixture
def audio(tmp_path):
    return make_audio(tmp_path / "snippet.m4a")


def make_service(language: str = "en") -> OpenAICompatibleASRService:
    return OpenAICompatibleASRService(lambda *a, **k: None, language=language)


def multipart_fields(request: httpx.Request) -> dict:
    """Form fields and the uploaded file of a multipart request"""
    raw = b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.read()
    message = BytesParser(policy=default_policy).parsebytes(raw)
    fields = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        fields[name] = part.get_content() if part.get_filename() is None else part.get_payload(decode=True)
    return fields


def wav_info(data: bytes):
    with wave.open(io.BytesIO(data)) as w:
        return w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()


# --- request shape ---------------------------------------------------------------------------


def test_normalize_base_url():
    assert normalize_base_url(" host:8000/v1/ ") == "http://host:8000/v1"
    assert normalize_base_url("https://api.example.com/v1/audio/transcriptions") == "https://api.example.com/v1"
    assert normalize_base_url("") == ""


def test_request_fields_send_only_what_is_set():
    settings = hosted.HostedSettings(BASE_URL, "", "", False, 4)
    assert request_fields(settings, "auto", "") == {"response_format": "json"}
    assert request_fields(settings, "", "") == {"response_format": "json"}

    settings = hosted.HostedSettings(BASE_URL, "", "whisper-1", False, 4)
    assert request_fields(settings, "de", "Kapitel 1 2 3") == {
        "response_format": "json",
        "model": "whisper-1",
        "language": "de",
        "prompt": "Kapitel 1 2 3",
    }


async def test_uploads_16k_mono_wav_with_settings(isolated_config, audio, httpx_mock):
    isolated_config.hosted_asr.api_key = "sk-test"
    isolated_config.hosted_asr.model = "Systran/faster-whisper-small.en"
    isolated_config.asr_options.use_bias_words = True
    isolated_config.asr_options.bias_words = "Chapter Prologue"
    httpx_mock.add_response(url=ENDPOINT, method="POST", json={"text": " Chapter 3. The Long Road Home \n"})

    async with make_service() as service:
        assert service.transcribe_file(audio) == "Chapter 3. The Long Road Home"

    request = httpx_mock.get_request()
    assert request.headers["authorization"] == "Bearer sk-test"
    fields = multipart_fields(request)
    assert fields["model"] == "Systran/faster-whisper-small.en"
    assert fields["language"] == "en"
    assert fields["prompt"] == "Chapter Prologue"
    assert fields["response_format"] == "json"
    channels, rate, width, frames = wav_info(fields["file"])
    assert (channels, rate, width) == (1, 16000, 2)
    assert abs(frames - 16000) < 1600


async def test_auto_language_and_no_key_are_left_out(isolated_config, audio, httpx_mock):
    httpx_mock.add_response(url=ENDPOINT, json={"text": "Prologue"})

    async with make_service(language="auto") as service:
        service.transcribe_file(audio)

    request = httpx_mock.get_request()
    assert "authorization" not in request.headers
    fields = multipart_fields(request)
    assert "language" not in fields and "model" not in fields and "prompt" not in fields


async def test_plain_text_response(audio, httpx_mock):
    httpx_mock.add_response(url=ENDPOINT, text="Chapter One\n", headers={"content-type": "text/plain"})

    async with make_service() as service:
        assert service.transcribe_file(audio) == "Chapter One"


# --- errors and retries ----------------------------------------------------------------------


async def test_rate_limit_is_retried_after_the_servers_delay(audio, httpx_mock, no_retry_sleep):
    httpx_mock.add_response(url=ENDPOINT, status_code=429, headers={"retry-after": "2"}, json={"error": "slow down"})
    httpx_mock.add_response(url=ENDPOINT, status_code=503)
    httpx_mock.add_response(url=ENDPOINT, json={"text": "Chapter Two"})

    async with make_service() as service:
        assert service.transcribe_file(audio) == "Chapter Two"

    assert no_retry_sleep[0] == 2.0
    assert 0 < no_retry_sleep[1] < 3
    assert len(httpx_mock.get_requests()) == 3


async def test_rejected_key_is_fatal(audio, httpx_mock):
    httpx_mock.add_response(
        url=ENDPOINT, status_code=401, json={"error": {"message": "Incorrect API key provided", "type": "auth"}}
    )

    async with make_service() as service:
        with pytest.raises(ASRFatalError, match="rejected the API key.*Incorrect API key provided"):
            service.transcribe_file(audio)


async def test_unreachable_server_is_fatal_without_retries(audio, httpx_mock, no_retry_sleep):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"), url=ENDPOINT)

    async with make_service() as service:
        with pytest.raises(ASRFatalError, match="Couldn't connect to http://asr.test/v1"):
            service.transcribe_file(audio)
    assert no_retry_sleep == []


async def test_dropped_connection_is_retried(audio, httpx_mock):
    # A kept-alive connection the server closed while idle
    httpx_mock.add_exception(httpx.RemoteProtocolError("Server disconnected without sending a response."))
    httpx_mock.add_response(url=ENDPOINT, json={"text": "Epilogue"})

    async with make_service() as service:
        assert service.transcribe_file(audio) == "Epilogue"


async def test_first_failure_is_fatal_but_later_ones_only_fail_the_snippet(audio, httpx_mock):
    detail = "Model 'whisper-1' is not installed locally. You can download the model using `POST /v1/models`"
    httpx_mock.add_response(url=ENDPOINT, status_code=404, json={"detail": detail})

    async with make_service() as service:
        with pytest.raises(ASRFatalError, match=re.escape(detail)):
            service.transcribe_file(audio)

    httpx_mock.add_response(url=ENDPOINT, json={"text": "Chapter One"})
    httpx_mock.add_response(url=ENDPOINT, status_code=400, json={"error": {"message": "Audio file is too short"}})
    async with make_service() as service:
        assert service.transcribe_file(audio) == "Chapter One"
        with pytest.raises(RuntimeError, match="Audio file is too short") as raised:
            service.transcribe_file(audio)
        assert not isinstance(raised.value, ASRFatalError)


def test_validation_errors_name_the_field():
    response = httpx.Response(
        422,
        json={"detail": [{"type": "missing", "loc": ["body", "model"], "msg": "Field required", "input": None}]},
    )
    assert hosted.error_detail(response) == "model: Field required"


async def test_missing_server_url_is_fatal(isolated_config):
    isolated_config.hosted_asr.base_url = ""
    with pytest.raises(ASRFatalError, match="No server URL"):
        async with make_service():
            pass


# --- batches ---------------------------------------------------------------------------------


async def test_batch_runs_requests_in_parallel_and_keeps_order(isolated_config, tmp_path, httpx_mock):
    isolated_config.hosted_asr.parallel_requests = 3
    files = [make_audio(tmp_path / f"s{i}.m4a", seconds=1 + i * 0.5) for i in range(6)]
    in_flight = 0
    peak = 0
    lock = threading.Lock()

    def respond(request: httpx.Request):
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        real_sleep(0.05)
        _, _, _, frames = wav_info(multipart_fields(request)["file"])
        with lock:
            in_flight -= 1
        return httpx.Response(200, json={"text": f"{round(frames / 8000) / 2} seconds"})

    httpx_mock.add_callback(respond, url=ENDPOINT, is_reusable=True)

    async with make_service() as service:
        transcripts = await service.transcribe(files)

    assert transcripts == [f"{1 + i * 0.5} seconds" for i in range(6)]
    assert 1 < peak <= 3


async def test_batch_stops_on_fatal_error(audio, httpx_mock):
    httpx_mock.add_response(url=ENDPOINT, status_code=401, is_reusable=True)

    async with make_service() as service:
        with pytest.raises(ASRFatalError):
            await service.transcribe([audio, audio, audio])


class FakeLocalService(ASRService):
    """A local service: one file at a time, some failing"""

    def __init__(self):
        super().__init__(lambda *a, **k: None, "", "en")
        self.order = []

    @property
    def service_name(self) -> str:
        return "Fake"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def transcribe_file(self, audio_file: str) -> str:
        self.order.append(audio_file)
        if audio_file == "bad":
            raise ValueError("decode failed")
        return audio_file.upper()

    def _transcribe_file(self, audio_file: str, retry_on_empty: bool = True) -> str:
        raise NotImplementedError


async def test_local_batch_is_sequential_and_marks_failures():
    service = FakeLocalService()
    assert await service.transcribe(["a", "bad", "c"]) == ["A", "[Transcription Error]", "C"]
    assert service.order == ["a", "bad", "c"]


# --- warm-service cache key ------------------------------------------------------------------


def test_config_key_follows_hosted_settings(isolated_config):
    key = asr_service_options.get_asr_config_key()
    isolated_config.hosted_asr.model = "whisper-large-v3"
    assert asr_service_options.get_asr_config_key() != key

    key = asr_service_options.get_asr_config_key()
    isolated_config.hosted_asr.api_key = "sk-new"
    assert asr_service_options.get_asr_config_key() != key

    # Hosted settings don't touch a local service's key
    isolated_config.user_preferences.preferred_asr_service = "whisper_cpp"
    key = asr_service_options.get_asr_config_key()
    isolated_config.hosted_asr.model = "other"
    assert asr_service_options.get_asr_config_key() == key


# --- model list and connection test -----------------------------------------------------------


def test_filter_transcription_models():
    speaches = {
        "data": [
            {"id": "Systran/faster-whisper-small.en", "task": "automatic-speech-recognition"},
            {"id": "istupakov/parakeet-tdt-0.6b-v2-onnx", "task": "automatic-speech-recognition"},
            {"id": "speaches-ai/Kokoro-82M-v1.0-ONNX", "task": "text-to-speech"},
        ]
    }
    assert filter_transcription_models(speaches) == [
        "istupakov/parakeet-tdt-0.6b-v2-onnx",
        "Systran/faster-whisper-small.en",
    ]

    openai = {"data": [{"id": "gpt-4o"}, {"id": "whisper-1"}, {"id": "gpt-4o-mini-transcribe"}, {"id": "tts-1"}]}
    assert filter_transcription_models(openai) == ["gpt-4o-mini-transcribe", "whisper-1"]

    # Nothing looks like a transcription model: offer everything rather than nothing
    assert filter_transcription_models({"data": [{"id": "my-model"}]}) == ["my-model"]
    assert filter_transcription_models({"object": "list"}) == []


async def test_list_models(httpx_mock):
    httpx_mock.add_response(url=f"{BASE_URL}/models", json={"data": [{"id": "whisper-large-v3"}]})
    assert await hosted.list_models(hosted.load_settings()) == ["whisper-large-v3"]

    # whisper.cpp's server has no /models
    httpx_mock.add_response(url=f"{BASE_URL}/models", status_code=404, text="File Not Found")
    assert await hosted.list_models(hosted.load_settings()) == []

    httpx_mock.add_response(url=f"{BASE_URL}/models", status_code=401)
    with pytest.raises(HostedASRError, match="API key"):
        await hosted.list_models(hosted.load_settings())


async def test_test_transcription_reports_the_server_error(httpx_mock):
    httpx_mock.add_response(url=ENDPOINT, json={"text": ""})
    assert await hosted.test_transcription(hosted.load_settings(), "en", "") >= 0

    httpx_mock.add_response(url=ENDPOINT, status_code=400, json={"error": {"message": "Invalid language 'xx'"}})
    with pytest.raises(HostedASRError, match="Invalid language 'xx'"):
        await hosted.test_transcription(hosted.load_settings(), "xx", "")


# --- routes ----------------------------------------------------------------------------------


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(config_routes.router, prefix="/api")
    return TestClient(app)


def test_settings_routes_mask_and_keep_the_key(client, isolated_config):
    isolated_config.hosted_asr.api_key = "sk-secret"

    body = client.get("/api/asr/hosted").json()
    assert body["api_key"] == "***"
    assert body["base_url"] == BASE_URL

    # A field left out keeps its saved value, so the masked key survives other edits
    body = client.put("/api/asr/hosted", json={"model": " whisper-1 ", "parallel_requests": 99}).json()
    assert body["model"] == "whisper-1"
    assert body["parallel_requests"] == hosted.MAX_PARALLEL_REQUESTS
    assert isolated_config.hosted_asr.api_key == "sk-secret"

    client.put("/api/asr/hosted", json={"api_key": ""})
    assert isolated_config.hosted_asr.api_key == ""
    assert client.get("/api/asr/hosted").json()["api_key"] == ""


def test_test_route(client, httpx_mock):
    httpx_mock.add_response(url=ENDPOINT, json={"text": ""})
    body = client.post("/api/asr/hosted/test").json()
    assert body["success"] is True
    assert body["message"].startswith("Connected")

    httpx_mock.add_exception(httpx.ConnectError("Connection refused"), url=ENDPOINT)
    body = client.post("/api/asr/hosted/test").json()
    assert body == {"success": False, "message": "Couldn't connect to http://asr.test/v1: Connection refused"}


def test_preferences_route_flags_the_hosted_service(client):
    services = client.get("/api/asr/preferences").json()["available_services"]
    flags = {s["service_id"]: s["hosted"] for s in services}
    assert flags[hosted.SERVICE_ID] is True
    assert flags["whisper_cpp"] is False
