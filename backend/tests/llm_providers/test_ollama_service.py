"""Tests for the Ollama provider's connection configuration.

Focused on host normalization and the skip-SSL-verification option, which is
forwarded to the underlying httpx client for self-signed certificate support.
"""

import pytest

from app.core import config as C
from app.services.llm_providers.ollama_service import OllamaService

HOST = "https://ollama.test:11434"


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    """Use an isolated default config for tests."""
    app_cfg = C.AppConfig()
    monkeypatch.setattr(C, "_app_config", app_cfg)
    return app_cfg


def make_service():
    return OllamaService(lambda *a, **k: None)


def test_host_normalization():
    svc = make_service()
    assert svc._get_host({"host": "localhost:11434"}) == "http://localhost:11434"
    assert svc._get_host({"host": HOST}) == HOST
    assert svc._get_host({"host": ""}) is None


def test_skip_ssl_verify_coercion(isolated_config):
    svc = make_service()
    assert svc._get_skip_ssl_verify({"skip_ssl_verify": True}) is True
    assert svc._get_skip_ssl_verify({"skip_ssl_verify": "false"}) is False
    # Falls back to the saved configuration when not in the passed config.
    isolated_config.llm.ollama.skip_ssl_verify = True
    assert svc._get_skip_ssl_verify({}) is True


def test_create_client_forwards_verify(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, host=None, **kwargs):
            seen["host"] = host
            seen["verify"] = kwargs.get("verify")

    monkeypatch.setattr("app.services.llm_providers.ollama_service.ollama.AsyncClient", FakeClient)

    make_service()._create_client(HOST, skip_ssl_verify=True)
    assert seen == {"host": HOST, "verify": False}

    make_service()._create_client(HOST, skip_ssl_verify=False)
    assert seen == {"host": HOST, "verify": True}


def test_create_client_uses_saved_skip_ssl(isolated_config, monkeypatch):
    isolated_config.llm.ollama.skip_ssl_verify = True

    seen = {}

    class FakeClient:
        def __init__(self, host=None, **kwargs):
            seen["verify"] = kwargs.get("verify")

    monkeypatch.setattr("app.services.llm_providers.ollama_service.ollama.AsyncClient", FakeClient)

    make_service()._create_client(HOST)
    assert seen["verify"] is False
