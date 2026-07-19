"""Tests for the LM Studio provider.

The provider talks to LM Studio's REST API over HTTP(S) so it can support
optional API token authentication and self-signed certificates. These tests
exercise the HTTP surface (model discovery, validation, and the streaming
chat-completions call) against a mocked endpoint.
"""

import json

import httpx
import pytest

from app.core import config as C
from app.services.llm_providers.lm_studio_service import LMStudioService

HOST = "http://lmstudio.test:1234"


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    """Use an isolated default config for tests."""
    app_cfg = C.AppConfig()
    monkeypatch.setattr(C, "_app_config", app_cfg)
    return app_cfg


@pytest.fixture
def configured(isolated_config):
    """Point the isolated config at the mocked endpoint."""
    isolated_config.llm.lm_studio.host = HOST
    isolated_config.llm.lm_studio.api_key = "lm-test-token"
    return isolated_config


def make_service():
    return LMStudioService(lambda *a, **k: None)


def sse(obj) -> bytes:
    """Encode a chat-completions object as a minimal SSE stream."""
    delta = {"choices": [{"delta": {"content": json.dumps(obj)}}]}
    return ("data: " + json.dumps(delta) + "\n\n" + "data: [DONE]\n\n").encode()


def test_host_normalization():
    svc = make_service()
    assert svc._get_host({"host": "localhost:1234"}) == "http://localhost:1234"
    assert svc._get_host({"host": "https://lms.example.com/"}) == "https://lms.example.com"
    assert svc._get_host({"host": ""}) is None


def test_skip_ssl_verify_coercion(configured):
    svc = make_service()
    assert svc._get_skip_ssl_verify({"skip_ssl_verify": True}) is True
    assert svc._get_skip_ssl_verify({"skip_ssl_verify": "false"}) is False
    # Falls back to the saved configuration when not in the passed config.
    configured.llm.lm_studio.skip_ssl_verify = True
    assert svc._get_skip_ssl_verify({}) is True


async def test_validate_config_missing_host():
    ok, msg = await make_service().validate_config(host="")
    assert ok is False
    assert "server URL" in msg


async def test_validate_config_success_sends_token(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/v1/models", json={"data": []})
    ok, _ = await make_service().validate_config(host=HOST, api_key="lm-test-token")
    assert ok is True
    assert httpx_mock.get_request().headers["Authorization"] == "Bearer lm-test-token"


async def test_validate_config_auth_failure(httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/v1/models", status_code=401)
    ok, msg = await make_service().validate_config(host=HOST, api_key="bad")
    assert ok is False
    assert "API token" in msg


async def test_get_available_models_filters_and_sorts(configured, httpx_mock):
    httpx_mock.add_response(
        url=f"{HOST}/api/v0/models",
        json={
            "data": [
                {"id": "qwen3-8b", "type": "llm", "arch": "qwen3", "max_context_length": 32768},
                {"id": "text-embedding", "type": "embeddings"},
                {"id": "Llama-3.1-8B", "type": "llm"},
                {"id": ""},
            ]
        },
    )
    models = await make_service().get_available_models()
    # Sorted case-insensitively; embeddings and empty ids are dropped.
    assert [m.id for m in models] == ["Llama-3.1-8B", "qwen3-8b"]
    assert models[1].context_length == 32768


async def test_get_available_models_falls_back_to_v1(configured, httpx_mock):
    httpx_mock.add_response(url=f"{HOST}/api/v0/models", status_code=404)
    httpx_mock.add_response(url=f"{HOST}/v1/models", json={"data": [{"id": "some-model"}]})
    models = await make_service().get_available_models()
    assert [m.id for m in models] == ["some-model"]


async def test_process_chapter_titles_happy_path(configured, httpx_mock):
    obj = [{"id": 0, "title": "Chapter 1"}, {"id": 1, "title": None}]
    httpx_mock.add_response(url=f"{HOST}/v1/chat/completions", content=sse(obj))

    result = await make_service().process_chapter_titles(["chapter one", "noise"], "qwen3-8b")
    assert result == ["Chapter 1", None]

    request = httpx_mock.get_request()
    payload = json.loads(request.content)
    assert payload["response_format"]["type"] == "json_schema"
    assert request.headers["Authorization"] == "Bearer lm-test-token"
    # The input is wrapped in the same {"chapters": [...]} shape the prompt describes.
    user_content = json.loads(payload["messages"][1]["content"].removeprefix("Input data:\n"))
    assert user_content == {"chapters": [{"id": 0, "title": "chapter one"}, {"id": 1, "title": "noise"}]}


async def test_process_chapter_titles_falls_back_without_response_format(configured, httpx_mock):
    # First attempt: backend rejects structured output.
    httpx_mock.add_response(
        url=f"{HOST}/v1/chat/completions",
        status_code=400,
        json={"error": "response_format is not supported by this model"},
    )
    # Second attempt: succeeds without it.
    obj = [{"id": 0, "title": "Chapter 1"}]
    httpx_mock.add_response(url=f"{HOST}/v1/chat/completions", content=sse(obj))

    result = await make_service().process_chapter_titles(["chapter one"], "some-model")
    assert result == ["Chapter 1"]

    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    assert "response_format" in json.loads(requests[0].content)
    assert "response_format" not in json.loads(requests[1].content)


async def test_process_chapter_titles_gpt_oss_skips_structured_output(configured, httpx_mock):
    obj = [{"id": 0, "title": "Chapter 1"}]
    httpx_mock.add_response(url=f"{HOST}/v1/chat/completions", content=sse(obj))

    result = await make_service().process_chapter_titles(["chapter one"], "openai/gpt-oss-20b")
    assert result == ["Chapter 1"]
    assert "response_format" not in json.loads(httpx_mock.get_request().content)


async def test_process_chapter_titles_empty_input():
    assert await make_service().process_chapter_titles([], "qwen3-8b") == []


async def test_validate_config_includes_server_error_detail(httpx_mock):
    httpx_mock.add_response(
        url=f"{HOST}/v1/models",
        status_code=500,
        json={"error": {"message": "Something exploded"}},
    )
    ok, msg = await make_service().validate_config(host=HOST)
    assert ok is False
    assert "HTTP 500" in msg
    assert "Something exploded" in msg


async def test_process_error_includes_server_message(configured, httpx_mock):
    # gpt-oss id keeps this to a single (unstructured) attempt.
    httpx_mock.add_response(
        url=f"{HOST}/v1/chat/completions",
        status_code=400,
        json={"error": {"message": "Model crashed"}},
    )
    # The not-loaded diagnosis runs for 400s; the model is loaded, so the
    # server's own message is surfaced instead.
    httpx_mock.add_response(
        url=f"{HOST}/api/v0/models",
        json={"data": [{"id": "openai/gpt-oss-20b", "type": "llm", "state": "loaded"}]},
    )

    with pytest.raises(Exception, match="Model crashed"):
        await make_service().process_chapter_titles(["chapter one"], "openai/gpt-oss-20b")


async def test_process_error_diagnoses_unloaded_model(configured, httpx_mock):
    httpx_mock.add_response(
        url=f"{HOST}/v1/chat/completions",
        status_code=404,
        json={"error": "model not found"},
    )
    httpx_mock.add_response(
        url=f"{HOST}/api/v0/models",
        json={"data": [{"id": "qwen3-8b", "type": "llm", "state": "not-loaded"}]},
    )

    with pytest.raises(Exception, match="JIT model loading"):
        await make_service().process_chapter_titles(["chapter one"], "qwen3-8b")


async def test_save_config_keeps_saved_token_when_field_omitted(configured, httpx_mock, monkeypatch):
    """Re-validating without touching the masked token field must not wipe it."""
    saved = {}
    monkeypatch.setattr(
        "app.core.config.save_llm_provider_config",
        lambda provider_id, cfg: saved.update({provider_id: cfg}) or True,
    )
    httpx_mock.add_response(url=f"{HOST}/v1/models", json={"data": []})

    # The frontend omits api_key when only e.g. the SSL checkbox changed.
    ok, _ = await make_service().save_config(host=HOST, skip_ssl_verify=True)
    assert ok is True
    assert saved["lm_studio"].api_key == "lm-test-token"
    assert saved["lm_studio"].skip_ssl_verify is True


async def test_save_config_clears_token_on_explicit_empty(configured, httpx_mock, monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "app.core.config.save_llm_provider_config",
        lambda provider_id, cfg: saved.update({provider_id: cfg}) or True,
    )
    httpx_mock.add_response(url=f"{HOST}/v1/models", json={"data": []})

    ok, _ = await make_service().save_config(host=HOST, api_key="")
    assert ok is True
    assert saved["lm_studio"].api_key == ""


async def test_skip_ssl_verify_disables_httpx_verification(configured, httpx_mock, monkeypatch):
    configured.llm.lm_studio.skip_ssl_verify = True
    httpx_mock.add_response(url=f"{HOST}/api/v0/models", json={"data": []})

    seen = {}
    original_init = httpx.AsyncClient.__init__

    def spy_init(self, *args, **kwargs):
        seen["verify"] = kwargs.get("verify", True)
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy_init)

    await make_service().get_available_models()
    assert seen["verify"] is False
