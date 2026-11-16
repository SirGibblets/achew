"""Fixtures for the MCP server tests: an isolated app config, and the AppState singleton with
its pipeline and the MCP job runner restored afterwards."""

import pytest

from app.app import get_app_state
from app.core import config as config_module
from app.core.config import AppConfig
from app.mcp_server.runtime import jobs


@pytest.fixture
def app_config(monkeypatch, tmp_path):
    """A fresh app config that saves under tmp_path instead of the real config file."""
    monkeypatch.setattr(config_module, "get_config_json_path", lambda: tmp_path / "app_config.json")
    config = AppConfig()
    # Set up as far as the app's step logic cares; nothing here talks to a server
    config.abs.url = "http://abs.test"
    config.abs.api_key = "test-key"
    monkeypatch.setattr(config_module, "_app_config", config)
    return config


@pytest.fixture
def app_state(app_config):
    state = get_app_state()
    previous = state.pipeline
    state.last_error = None
    state.last_progress = None
    yield state
    if jobs.task is not None and not jobs.task.done():
        jobs.task.cancel()
    jobs.task = None
    jobs.error = None
    if state.pipeline is not None and state.pipeline is not previous:
        state.pipeline.cleanup_all_files()
    state.pipeline = previous
