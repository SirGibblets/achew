"""Tests for the generic OpenAI-compatible provider.

Exercises the HTTP surface (model discovery, validation, and the streaming
chat-completions call) against a mocked endpoint, including the fallback that
retries without ``response_format`` when a backend rejects it.
"""

import json

import pytest

from app.core import config as C
from app.services.llm_providers.openai_compatible_service import OpenAICompatibleService

BASE_URL = "http://litellm.test/v1"


@pytest.fixture
def configured(monkeypatch):
    """Install a saved config pointing at the mocked endpoint."""
    app_cfg = C.AppConfig()
    app_cfg.llm.openai_compatible.base_url = BASE_URL
    app_cfg.llm.openai_compatible.api_key = "sk-test"
    monkeypatch.setattr(C, "_app_config", app_cfg)
    return app_cfg


def make_service():
    return OpenAICompatibleService(lambda *a, **k: None)


def sse(obj) -> bytes:
    """Encode a chat-completions object as a minimal SSE stream."""
    delta = {"choices": [{"delta": {"content": json.dumps(obj)}}]}
    return ("data: " + json.dumps(delta) + "\n\n" + "data: [DONE]\n\n").encode()


def test_base_url_normalization():
    svc = make_service()
    assert svc._get_base_url({"base_url": "host:4000/v1/"}) == "http://host:4000/v1"
    assert svc._get_base_url({"base_url": "https://x/v1"}) == "https://x/v1"
    assert svc._get_base_url({"base_url": ""}) is None


async def test_validate_config_missing_base_url():
    ok, msg = await make_service().validate_config(base_url="")
    assert ok is False
    assert "Base URL" in msg


async def test_validate_config_success(httpx_mock):
    httpx_mock.add_response(url=f"{BASE_URL}/models", json={"data": []})
    ok, msg = await make_service().validate_config(base_url=BASE_URL, api_key="sk-test")
    assert ok is True


async def test_validate_config_auth_failure(httpx_mock):
    httpx_mock.add_response(url=f"{BASE_URL}/models", status_code=401)
    ok, msg = await make_service().validate_config(base_url=BASE_URL, api_key="bad")
    assert ok is False
    assert "Authentication" in msg


async def test_get_available_models_sorted(configured, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE_URL}/models",
        json={"data": [{"id": "llama-3.1-70b"}, {"id": "gpt-4o-mini"}, {"id": ""}]},
    )
    models = await make_service().get_available_models()
    # Sorted case-insensitively; the entry with an empty id is dropped.
    assert [m.id for m in models] == ["gpt-4o-mini", "llama-3.1-70b"]


async def test_process_chapter_titles_happy_path(configured, httpx_mock):
    obj = {"chapters": [{"id": 0, "title": "Chapter 1"}, {"id": 1, "title": None}]}
    httpx_mock.add_response(url=f"{BASE_URL}/chat/completions", content=sse(obj))

    result = await make_service().process_chapter_titles(["chapter one", "noise"], "gpt-4o-mini")
    assert result == ["Chapter 1", None]

    request = httpx_mock.get_request()
    assert json.loads(request.content)["response_format"] == {"type": "json_object"}


async def test_process_chapter_titles_falls_back_without_response_format(configured, httpx_mock):
    # First attempt: backend rejects response_format.
    httpx_mock.add_response(
        url=f"{BASE_URL}/chat/completions",
        status_code=400,
        json={"error": {"message": "response_format is not supported by this model"}},
    )
    # Second attempt: succeeds without it.
    obj = {"chapters": [{"id": 0, "title": "Chapter 1"}]}
    httpx_mock.add_response(url=f"{BASE_URL}/chat/completions", content=sse(obj))

    result = await make_service().process_chapter_titles(["chapter one"], "some-model")
    assert result == ["Chapter 1"]

    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    assert "response_format" in json.loads(requests[0].content)
    assert "response_format" not in json.loads(requests[1].content)


async def test_process_chapter_titles_empty_input():
    assert await make_service().process_chapter_titles([], "gpt-4o-mini") == []
