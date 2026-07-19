"""Tests for the OpenRouter provider's streaming chat-completions call.

Focused on the response-format fallback chain: strict ``json_schema`` first,
then ``json_object``, then no ``response_format`` — advancing on both HTTP 400
rejections and accepted-but-unparseable responses.
"""

import json

import pytest

from app.core import config as C
from app.services.llm_providers.openrouter_service import OpenRouterService

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    """Use an isolated default config for tests."""
    app_cfg = C.AppConfig()
    monkeypatch.setattr(C, "_app_config", app_cfg)
    return app_cfg


@pytest.fixture
def configured(isolated_config):
    """Install an API key so the provider gets past its config check."""
    isolated_config.llm.openrouter.api_key = "sk-or-test"
    return isolated_config


def make_service():
    return OpenRouterService(lambda *a, **k: None)


def sse(obj) -> bytes:
    """Encode a chat-completions object as a minimal SSE stream."""
    delta = {"choices": [{"delta": {"content": json.dumps(obj)}}]}
    return ("data: " + json.dumps(delta) + "\n\n" + "data: [DONE]\n\n").encode()


async def test_process_chapter_titles_happy_path(configured, httpx_mock):
    obj = {"chapters": [{"id": 0, "title": "Chapter 1"}, {"id": 1, "title": None}]}
    httpx_mock.add_response(url=CHAT_URL, content=sse(obj))

    result = await make_service().process_chapter_titles(["chapter one", "noise"], "openai/gpt-4o-mini")
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
            url=CHAT_URL,
            status_code=400,
            json={"error": {"message": message}},
        )
    # Third attempt: succeeds with no response_format at all.
    obj = {"chapters": [{"id": 0, "title": "Chapter 1"}]}
    httpx_mock.add_response(url=CHAT_URL, content=sse(obj))

    result = await make_service().process_chapter_titles(["chapter one"], "some/model")
    assert result == ["Chapter 1"]

    requests = httpx_mock.get_requests()
    assert len(requests) == 3
    assert json.loads(requests[0].content)["response_format"]["type"] == "json_schema"
    assert json.loads(requests[1].content)["response_format"] == {"type": "json_object"}
    assert "response_format" not in json.loads(requests[2].content)


async def test_process_chapter_titles_retries_on_unparseable_shape(configured, httpx_mock):
    # A model can accept the response_format yet return the wrong shape; the
    # provider must fall back to the next attempt, not hard-fail.
    httpx_mock.add_response(url=CHAT_URL, content=sse({"id": 0, "title": "Opening Credits"}))
    obj = {"chapters": [{"id": 0, "title": "Opening Credits"}]}
    httpx_mock.add_response(url=CHAT_URL, content=sse(obj))

    result = await make_service().process_chapter_titles(["opening credits"], "some/model")
    assert result == ["Opening Credits"]
    assert len(httpx_mock.get_requests()) == 2


async def test_thinking_models_get_reasoning_budget(configured, httpx_mock):
    obj = {"chapters": [{"id": 0, "title": "Chapter 1"}]}
    httpx_mock.add_response(url=CHAT_URL, content=sse(obj))

    await make_service().process_chapter_titles(["chapter one"], "some/model-thinking")

    payload = json.loads(httpx_mock.get_request().content)
    assert payload["reasoning"] == {"max_tokens": 1024}


async def test_process_chapter_titles_empty_input():
    assert await make_service().process_chapter_titles([], "openai/gpt-4o-mini") == []
