"""Tests for the OpenAI provider's model filtering, display order and
reasoning-effort selection."""

from types import SimpleNamespace

import pytest

from app.services.llm_providers import openai_service as svc
from app.services.llm_providers.openai_service import OpenAIService


class FakeModels:
    def __init__(self, ids=None, error=None):
        self._ids = ids or []
        self._error = error

    async def list(self):
        if self._error:
            raise self._error
        return SimpleNamespace(data=[SimpleNamespace(id=mid) for mid in self._ids])


def make_service(monkeypatch, **models_kwargs):
    service = OpenAIService(lambda *a, **k: None)
    client = SimpleNamespace(models=FakeModels(**models_kwargs))
    monkeypatch.setattr(service, "_create_client", lambda *a, **k: client)
    return service


async def test_get_available_models_orders_named_tiers_cheapest_first(monkeypatch):
    ids = [
        "gpt-6-astra",
        "gpt-6-sol",
        "gpt-6-luna",
        "gpt-6.1-sol",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.4",
        "gpt-5.4-pro",
        "gpt-5.4-nano",
        "gpt-5.4-mini",
    ]
    models = await make_service(monkeypatch, ids=ids).get_available_models()

    assert [m.id for m in models] == [
        "gpt-6.1-sol",
        "gpt-6-luna",
        "gpt-6-sol",
        "gpt-6-astra",
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
        "gpt-5.4-mini",
        "gpt-5.4",
        "gpt-5.4-nano",
        "gpt-5.4-pro",
    ]


@pytest.mark.parametrize(
    "model_id, family",
    [
        ("gpt-6-astra", "gpt-6"),
        ("gpt-6.1-sol", "gpt-6.1"),
        ("gpt-6-luna", "gpt-6"),
        ("gpt-5.6-terra", "gpt-5.6"),
        ("gpt-5.4-mini", "gpt-5.4"),
        ("gpt-5.4", "gpt-5.4"),
    ],
)
def test_family_prefix_strips_tier_suffix(model_id, family):
    assert svc._family_prefix(model_id) == family


@pytest.mark.parametrize(
    "model_id",
    ["gpt-5.6-cyber", "gpt-live-1", "gpt-daybreak-red-latest", "gpt-realtime-2.1-mini", "gpt-6-luna-2026-09-01"],
)
def test_specialized_models_are_excluded(model_id):
    assert not svc._is_supported_openai_model(model_id)


@pytest.mark.parametrize("model_id", ["gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna", "gpt-5.6-terra"])
def test_named_tiers_are_supported(model_id):
    assert svc._is_supported_openai_model(model_id)


@pytest.mark.parametrize(
    "model_id, effort",
    [
        # Astra and Sol accept low through max; Luna also accepts none.
        ("gpt-6-astra", "low"),
        ("gpt-6.1-sol", "low"),
        ("gpt-6-luna", "low"),
        ("gpt-5.4-mini", "low"),
        ("gpt-5.4-pro", "medium"),
        ("gpt-4.1", None),
    ],
)
def test_reasoning_effort_for(model_id, effort):
    assert svc._reasoning_effort_for(model_id) == effort


async def test_get_available_models_fallback_on_error(monkeypatch):
    models = await make_service(monkeypatch, error=RuntimeError("boom")).get_available_models()
    assert [m.id for m in models] == ["gpt-5.4-mini"]
