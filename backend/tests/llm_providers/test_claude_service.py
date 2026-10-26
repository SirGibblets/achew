"""Tests for the Claude provider's model listing order and structured-output
request."""

import json
from types import SimpleNamespace

import anthropic
import httpx2
from anthropic.types import ModelInfo as AnthropicModelInfo

from app.services.llm_providers.claude_service import ClaudeService


def api_model(model_id, line=None, with_line=True):
    data = {"id": model_id, "created_at": "2026-01-01T00:00:00Z", "display_name": model_id, "type": "model"}
    if with_line:
        data["line"] = line
    # model_construct skips validation of the capability fields these tests don't need.
    return AnthropicModelInfo.model_construct(**data)


def make_service(monkeypatch, data):
    async def list_models(**kwargs):
        return SimpleNamespace(data=data)

    service = ClaudeService(lambda *a, **k: None)
    client = SimpleNamespace(models=SimpleNamespace(list=list_models))
    monkeypatch.setattr(service, "_get_api_key", lambda *a, **k: "sk-ant-test")
    monkeypatch.setattr(service, "_create_client", lambda *a, **k: client)
    return service


async def test_sonnet_line_sorts_first_keeping_api_order(monkeypatch):
    # The Models API lists newest first.
    data = [
        api_model("claude-fable-5-1", "fable"),
        api_model("claude-haiku-5-5", "haiku"),
        api_model("claude-sonnet-5-5", "sonnet"),
        api_model("claude-opus-5-5", "opus"),
        api_model("claude-sonnet-5", "sonnet"),
        api_model("claude-sonnet-4-6", "sonnet"),
    ]
    models = await make_service(monkeypatch, data).get_available_models()

    assert [m.id for m in models] == [
        "claude-sonnet-5-5",
        "claude-sonnet-5",
        "claude-sonnet-4-6",
        "claude-fable-5-1",
        "claude-haiku-5-5",
        "claude-opus-5-5",
    ]


async def test_line_field_takes_precedence_over_id(monkeypatch):
    data = [
        api_model("claude-opus-5-5", "opus"),
        api_model("claude-future-1", "sonnet"),
    ]
    models = await make_service(monkeypatch, data).get_available_models()
    assert [m.id for m in models] == ["claude-future-1", "claude-opus-5-5"]


async def test_falls_back_to_id_without_line_field(monkeypatch):
    data = [
        api_model("claude-opus-5-5", with_line=False),
        api_model("claude-sonnet-5-5", with_line=False),
    ]
    models = await make_service(monkeypatch, data).get_available_models()
    assert [m.id for m in models] == ["claude-sonnet-5-5", "claude-opus-5-5"]


def sse(text: str) -> bytes:
    """A minimal Messages stream whose single text block is `text`."""
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-5-5",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
        (
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 1},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


async def test_process_chapter_titles_requests_ga_structured_output(monkeypatch):
    requests = []
    body = {"chapters": [{"id": 0, "title": "Chapter 1"}, {"id": 1, "title": None}]}

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=sse(json.dumps(body)))

    client = anthropic.AsyncAnthropic(
        api_key="sk-ant-test",
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    service = ClaudeService(lambda *a, **k: None)
    monkeypatch.setattr(service, "_get_api_key", lambda *a, **k: "sk-ant-test")
    monkeypatch.setattr(service, "_create_client", lambda *a, **k: client)

    result = await service.process_chapter_titles(["chapter one", "noise"], "claude-sonnet-5-5")
    assert result == ["Chapter 1", None]

    (request,) = requests
    assert request.url.path == "/v1/messages"
    assert request.headers["anthropic-version"] == "2026-10-21"
    assert "anthropic-beta" not in request.headers
    payload = json.loads(request.content)
    assert "output_format" not in payload
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert "chapters" in payload["output_config"]["format"]["schema"]["properties"]
