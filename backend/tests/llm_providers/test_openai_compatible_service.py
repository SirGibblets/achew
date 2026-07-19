"""Tests for the generic OpenAI-compatible provider.

Exercises the HTTP surface (model discovery, validation, and the streaming
chat-completions call) against a mocked endpoint, including the fallback chain
that retries with progressively simpler ``response_format`` values when a
backend rejects one (HTTP 400) or accepts it but produces an unparseable shape.
"""

import asyncio
import json

import httpx
import pytest

from app.core import config as C
from app.services.llm_providers import openai_compatible_service
from app.services.llm_providers.openai_compatible_service import OpenAICompatibleService

BASE_URL = "http://litellm.test/v1"


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    """Use an isolated default config for tests."""
    app_cfg = C.AppConfig()
    monkeypatch.setattr(C, "_app_config", app_cfg)
    return app_cfg


@pytest.fixture
def configured(isolated_config):
    """Point the isolated config at the mocked endpoint."""
    isolated_config.llm.openai_compatible.base_url = BASE_URL
    isolated_config.llm.openai_compatible.api_key = "sk-test"
    return isolated_config


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

    # The first attempt requests strict structured output, and the input is
    # wrapped in the same {"chapters": [...]} shape the prompt describes.
    payload = json.loads(httpx_mock.get_request().content)
    assert payload["response_format"]["type"] == "json_schema"
    user_content = json.loads(payload["messages"][1]["content"])
    assert user_content == {"chapters": [{"id": 0, "title": "chapter one"}, {"id": 1, "title": "noise"}]}


async def test_process_chapter_titles_falls_back_through_format_chain(configured, httpx_mock):
    # First two attempts: backend rejects the schema, then json_object.
    for message in ("json_schema is not supported", "response_format is not supported by this model"):
        httpx_mock.add_response(
            url=f"{BASE_URL}/chat/completions",
            status_code=400,
            json={"error": {"message": message}},
        )
    # Third attempt: succeeds with no response_format at all.
    obj = {"chapters": [{"id": 0, "title": "Chapter 1"}]}
    httpx_mock.add_response(url=f"{BASE_URL}/chat/completions", content=sse(obj))

    result = await make_service().process_chapter_titles(["chapter one"], "some-model")
    assert result == ["Chapter 1"]

    requests = httpx_mock.get_requests()
    assert len(requests) == 3
    assert json.loads(requests[0].content)["response_format"]["type"] == "json_schema"
    assert json.loads(requests[1].content)["response_format"] == {"type": "json_object"}
    assert "response_format" not in json.loads(requests[2].content)


async def test_process_chapter_titles_retries_on_unparseable_shape(configured, httpx_mock):
    # A backend can accept the response_format yet return the wrong shape —
    # e.g. Ollama's json_object grammar ends generation after a single object.
    # The provider must fall back to the next attempt, not hard-fail.
    httpx_mock.add_response(
        url=f"{BASE_URL}/chat/completions",
        content=sse({"id": 0, "title": "Opening Credits"}),
    )
    obj = {"chapters": [{"id": 0, "title": "Opening Credits"}]}
    httpx_mock.add_response(url=f"{BASE_URL}/chat/completions", content=sse(obj))

    result = await make_service().process_chapter_titles(["opening credits"], "llama3.1")
    assert result == ["Opening Credits"]
    assert len(httpx_mock.get_requests()) == 2


async def test_process_chapter_titles_strips_markdown_fences(configured, httpx_mock):
    obj = {"chapters": [{"id": 0, "title": "Chapter 1"}]}
    fenced = "```json\n" + json.dumps(obj) + "\n```"
    delta = {"choices": [{"delta": {"content": fenced}}]}
    content = ("data: " + json.dumps(delta) + "\n\n" + "data: [DONE]\n\n").encode()
    httpx_mock.add_response(url=f"{BASE_URL}/chat/completions", content=content)

    result = await make_service().process_chapter_titles(["chapter one"], "gpt-4o-mini")
    assert result == ["Chapter 1"]


async def test_process_chapter_titles_empty_input():
    assert await make_service().process_chapter_titles([], "gpt-4o-mini") == []


@pytest.mark.parametrize("reasoning_field", ["reasoning_content", "reasoning"])
async def test_process_chapter_titles_reports_thinking(configured, httpx_mock, reasoning_field):
    obj = {"chapters": [{"id": 0, "title": "Chapter 1"}]}
    events = [
        {"choices": [{"delta": {reasoning_field: "hmm, let me think"}}]},
        {"choices": [{"delta": {"content": json.dumps(obj)}}]},
    ]
    body = "".join("data: " + json.dumps(e) + "\n\n" for e in events) + "data: [DONE]\n\n"
    httpx_mock.add_response(url=f"{BASE_URL}/chat/completions", content=body.encode())

    messages = []
    svc = OpenAICompatibleService(lambda step, pct, msg, details: messages.append(msg))
    result = await svc.process_chapter_titles(["chapter one"], "deepseek-r1")

    # Reasoning deltas surface as a status update and stay out of the parsed content.
    assert result == ["Chapter 1"]
    assert "Thinking…" in messages


async def test_first_token_watchdog_notifies_when_stream_is_slow(monkeypatch):
    monkeypatch.setattr(openai_compatible_service, "FIRST_TOKEN_WATCHDOG_SECONDS", 0.0)

    messages = []
    svc = OpenAICompatibleService(lambda step, pct, msg, details: messages.append(msg))
    task = svc._start_first_token_watchdog()
    await asyncio.sleep(0.05)

    assert task.done()
    assert any("loading the model" in m for m in messages)


async def test_skip_ssl_verify_disables_httpx_verification(configured, httpx_mock, monkeypatch):
    configured.llm.openai_compatible.skip_ssl_verify = True
    httpx_mock.add_response(url=f"{BASE_URL}/models", json={"data": []})

    seen = {}
    original_init = httpx.AsyncClient.__init__

    def spy_init(self, *args, **kwargs):
        seen["verify"] = kwargs.get("verify", True)
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy_init)

    await make_service().get_available_models()
    assert seen["verify"] is False
