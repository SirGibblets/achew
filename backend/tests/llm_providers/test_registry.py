"""Tests for the provider registry's model list cache.

Self-hosted providers (Ollama, LM Studio, OpenAI-compatible) opt out of
caching via ``CACHE_MODELS`` so models the user adds or removes show up
immediately; cloud providers keep the cache since their catalogs change
rarely and can be slow to fetch.
"""

from app.services.llm_providers.base import ModelInfo
from app.services.llm_providers.lm_studio_service import LMStudioService
from app.services.llm_providers.ollama_service import OllamaService
from app.services.llm_providers.openai_compatible_service import OpenAICompatibleService
from app.services.llm_providers.registry import ProviderRegistry


def test_self_hosted_providers_opt_out_of_model_cache():
    assert OllamaService.CACHE_MODELS is False
    assert LMStudioService.CACHE_MODELS is False
    assert OpenAICompatibleService.CACHE_MODELS is False


async def test_get_provider_models_skips_cache_for_self_hosted(monkeypatch):
    registry = ProviderRegistry()
    calls = {"ollama": 0, "openai": 0}

    async def fake_ollama_models(self):
        calls["ollama"] += 1
        return [ModelInfo(id="local-model", name="local-model")]

    async def fake_openai_models(self):
        calls["openai"] += 1
        return [ModelInfo(id="gpt-test", name="gpt-test")]

    monkeypatch.setattr(
        "app.services.llm_providers.ollama_service.OllamaService.get_available_models", fake_ollama_models
    )
    monkeypatch.setattr(
        "app.services.llm_providers.openai_service.OpenAIService.get_available_models", fake_openai_models
    )

    # Self-hosted: every call fetches fresh.
    await registry.get_provider_models("ollama", host="http://localhost:11434")
    await registry.get_provider_models("ollama", host="http://localhost:11434")
    assert calls["ollama"] == 2

    # Cloud provider: second call is served from the cache.
    await registry.get_provider_models("openai", api_key="sk-test")
    await registry.get_provider_models("openai", api_key="sk-test")
    assert calls["openai"] == 1
