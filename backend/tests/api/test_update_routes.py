"""Tests for in-app updates (app/api/routes/update.py).

Only installs started by run.sh / run.bat (which name a restart file in ACHEW_RESTART_FILE)
can update from the app. A successful update writes the restart file, then shuts the server
down so the run script starts the new version; the shutdown is stubbed out here.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import update as update_routes
from app.core import updater


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv(update_routes.DOCKER_ENV, raising=False)
    monkeypatch.setattr(update_routes, "get_app_version", lambda: "1.0.0")
    monkeypatch.setattr(update_routes.updater, "inspect_install", lambda: updater.InstallInfo("archive", "1.0.0"))
    monkeypatch.delenv(update_routes.RESTART_FILE_ENV, raising=False)
    app = FastAPI()
    app.include_router(update_routes.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def shutdowns(monkeypatch):
    calls = []
    monkeypatch.setattr(update_routes, "_shut_down", lambda: calls.append(True))
    return calls


@pytest.fixture
def restart_file(tmp_path, monkeypatch):
    path = tmp_path / ".toolchain" / "restart-requested"
    monkeypatch.setenv(update_routes.RESTART_FILE_ENV, str(path))
    return path


class TestStatus:
    def test_offers_in_app_updates_when_a_run_script_can_restart_achew(self, client, restart_file):
        status = client.get("/api/update").json()

        assert status == {"install": "archive", "version": "1.0.0", "can_update": True, "reason": None, "command": None}

    def test_offers_the_terminal_command_when_started_some_other_way(self, client):
        status = client.get("/api/update").json()

        assert status["can_update"] is False
        assert "run.sh or run.bat" in status["reason"]
        assert "--update" in status["command"]

    def test_explains_install_problems_without_a_command(self, client, restart_file, monkeypatch):
        problem = "This git checkout has local changes."
        monkeypatch.setattr(
            update_routes.updater, "inspect_install", lambda: updater.InstallInfo("git", "1.0.0", problem)
        )

        status = client.get("/api/update").json()

        assert (status["can_update"], status["reason"], status["command"]) == (False, problem, None)

    def test_docker_installs_update_by_pulling_the_image(self, client, restart_file, monkeypatch):
        monkeypatch.setenv(update_routes.DOCKER_ENV, "1")

        status = client.get("/api/update").json()

        assert (status["install"], status["can_update"]) == ("docker", False)


class TestRunUpdate:
    def test_restarts_after_updating(self, client, restart_file, shutdowns, monkeypatch):
        monkeypatch.setattr(update_routes.updater, "update", lambda log: updater.UpdateResult(True, "1.0.0", "1.1.0"))

        response = client.post("/api/update")

        assert response.json() == {"updated": True, "version": "1.1.0"}
        assert restart_file.exists()

    def test_stays_up_when_already_up_to_date(self, client, restart_file, shutdowns, monkeypatch):
        monkeypatch.setattr(update_routes.updater, "update", lambda log: updater.UpdateResult(False, "1.0.0", "1.0.0"))

        response = client.post("/api/update")

        assert response.json() == {"updated": False, "version": "1.0.0"}
        assert not restart_file.exists()
        assert shutdowns == []

    def test_reports_update_errors(self, client, restart_file, shutdowns, monkeypatch):
        def fail(log):
            raise updater.UpdateError("Couldn't look up the latest Achew release: offline")

        monkeypatch.setattr(update_routes.updater, "update", fail)

        response = client.post("/api/update")

        assert response.status_code == 409
        assert response.json()["detail"] == "Couldn't look up the latest Achew release: offline"
        assert not restart_file.exists()

    def test_refuses_without_a_run_script_to_restart_achew(self, client, shutdowns, monkeypatch):
        monkeypatch.setattr(update_routes.updater, "update", lambda log: pytest.fail("updated"))

        response = client.post("/api/update")

        assert response.status_code == 409
