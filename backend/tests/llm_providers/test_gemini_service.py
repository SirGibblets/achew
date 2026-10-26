"""Tests for the Gemini provider's model filtering and display order."""

from types import SimpleNamespace

from app.services.llm_providers.gemini_service import GeminiService


def api_model(name, actions=("generateContent",)):
    return SimpleNamespace(
        name=f"models/{name}",
        display_name=name,
        description=None,
        supported_actions=list(actions),
    )


def make_service(monkeypatch, data):
    service = GeminiService(lambda *a, **k: None)
    client = SimpleNamespace(models=SimpleNamespace(list=lambda: data))
    monkeypatch.setattr(service, "_get_api_key", lambda *a, **k: "test-key")
    monkeypatch.setattr(service, "_create_client", lambda *a, **k: client)
    return service


async def test_orders_by_tier_then_newest_version(monkeypatch):
    data = [
        api_model("gemini-4-argon"),
        api_model("gemini-3.1-pro-preview"),
        api_model("gemini-2.5-pro"),
        api_model("gemini-3.8-flash"),
        api_model("gemini-3.6-flash"),
        api_model("gemini-2.5-flash"),
        api_model("gemini-3.5-flash-lite"),
        api_model("gemini-3.1-flash-lite"),
        api_model("gemini-flash-latest"),
    ]
    models = await make_service(monkeypatch, data).get_available_models()

    assert [m.id.removeprefix("models/") for m in models] == [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-2.5-pro",
        "gemini-4-argon",
    ]


async def test_filters_unsupported_models(monkeypatch):
    data = [
        api_model("gemini-3.8-flash"),
        api_model("gemini-3.8-flash-tts"),
        api_model("gemini-3.8-live"),
        api_model("gemini-embedding-001", actions=("embedContent",)),
        api_model("gemini-3.1-flash-image"),
    ]
    models = await make_service(monkeypatch, data).get_available_models()
    assert [m.id for m in models] == ["models/gemini-3.8-flash"]
