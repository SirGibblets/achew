"""Tests for the Copilot provider's token validation.

Under PAT auth the CLI runtime lists no models (older runtimes listed only
"auto"), so validation falls back to the Copilot models API.
"""

from types import SimpleNamespace

import httpx
import pytest

from app.services.llm_providers.base import ModelInfo
from app.services.llm_providers.copilot_service import CopilotService


class FakeClient:
    def __init__(self, models=None, error=None):
        self._models = models or []
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def list_models(self):
        if self._error:
            raise self._error
        return [SimpleNamespace(id=mid) for mid in self._models]


def make_service(monkeypatch, client, api_result):
    service = CopilotService(lambda *a, **k: None)

    async def no_runtime():
        return False

    async def fetch_models(token):
        if isinstance(api_result, Exception):
            raise api_result
        return api_result

    monkeypatch.setattr(service, "_ensure_runtime", no_runtime)
    monkeypatch.setattr(service, "_create_client", lambda *a, **k: client)
    monkeypatch.setattr(service, "_fetch_models_from_api", fetch_models)
    return service


def http_error(status):
    request = httpx.Request("GET", "https://api.githubcopilot.com/models")
    return httpx.HTTPStatusError("error", request=request, response=httpx.Response(status, request=request))


API_MODELS = [ModelInfo(id="gpt-6-luna", name="GPT-6 Luna")]


@pytest.mark.parametrize("runtime_models", [[], ["auto"]])
async def test_pat_without_runtime_models_validates_through_api(monkeypatch, runtime_models):
    service = make_service(monkeypatch, FakeClient(runtime_models), API_MODELS)
    assert await service.validate_config(api_key="github_pat_test") == (True, "Valid")


async def test_runtime_models_skip_api(monkeypatch):
    service = make_service(monkeypatch, FakeClient(["auto", "gpt-6-luna"]), http_error(500))
    assert await service.validate_config(api_key="github_pat_test") == (True, "Valid")


@pytest.mark.parametrize("status", [401, 403])
async def test_api_auth_failure_is_not_authorized(monkeypatch, status):
    service = make_service(monkeypatch, FakeClient([]), http_error(status))
    valid, message = await service.validate_config(api_key="github_pat_test")
    assert not valid
    assert message.startswith("Not authorized")


async def test_no_models_anywhere_is_invalid(monkeypatch):
    service = make_service(monkeypatch, FakeClient([]), [])
    valid, message = await service.validate_config(api_key="github_pat_test")
    assert not valid
    assert message.startswith("Unable to validate")


async def test_runtime_auth_failure_is_not_authorized(monkeypatch):
    error = RuntimeError("Request models.list failed with message: Not authenticated. Please authenticate first.")
    service = make_service(monkeypatch, FakeClient(error=error), API_MODELS)
    valid, message = await service.validate_config(api_key="github_pat_test")
    assert not valid
    assert message.startswith("Not authorized")
