"""Tests for the /mcp endpoint (app/mcp_server/endpoint.py) and its settings routes
(app/api/routes/mcp.py): off until turned on, a bearer token on every request, and token
regeneration locking out the old one."""

import json
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Route

from app.api.routes import mcp as mcp_routes
from app.mcp_server import MCP_PATH, MCPEndpoint, create_mcp_server

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    },
}


@pytest.fixture
def client(app_config):
    endpoint = MCPEndpoint(create_mcp_server())

    @asynccontextmanager
    async def lifespan(_app):
        async with endpoint.lifespan():
            yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(mcp_routes.router, prefix="/api")
    app.router.routes.append(Route(MCP_PATH, endpoint=endpoint, methods=["GET", "POST", "DELETE"]))
    with TestClient(app) as test_client:
        yield test_client


def _initialize(client, token=None, extra_headers=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
    return client.post(MCP_PATH, headers=headers, content=json.dumps(INITIALIZE))


def _message(response) -> dict:
    """The JSON-RPC message from a JSON or single-event SSE response."""
    if response.headers["content-type"].startswith("application/json"):
        return response.json()
    data = [line[len("data:") :].strip() for line in response.text.splitlines() if line.startswith("data:")]
    return json.loads(data[-1])


def test_off_by_default(client):
    response = _initialize(client, token="anything")
    assert response.status_code == 404
    assert "turned off" in response.json()["error"]
    assert client.get("/api/mcp/settings").json() == {
        "enabled": False,
        "allow_submit": True,
        "token": "",
        "path": "/mcp",
    }


def test_turning_on_generates_a_token_that_is_required(client, app_config, tmp_path):
    settings = client.put("/api/mcp/settings", json={"enabled": True}).json()
    token = settings["token"]
    assert settings["enabled"] is True and len(token) >= 40
    assert json.loads((tmp_path / "app_config.json").read_text())["mcp"]["token"] == token

    assert _initialize(client).status_code == 403
    assert _initialize(client, token="wrong").status_code == 403

    response = _initialize(client, token=token)
    assert response.status_code == 200
    message = _message(response)
    assert message["result"]["serverInfo"]["name"] == "achew"
    assert "Audiobookshelf" in message["result"]["instructions"]

    # Turning it off and on again keeps the same token
    client.put("/api/mcp/settings", json={"enabled": False})
    assert _initialize(client, token=token).status_code == 404
    assert client.put("/api/mcp/settings", json={"enabled": True}).json()["token"] == token


def test_regenerating_the_token_locks_out_the_old_one(client):
    old = client.put("/api/mcp/settings", json={"enabled": True}).json()["token"]
    new = client.post("/api/mcp/settings/token").json()["token"]
    assert new != old
    assert _initialize(client, token=old).status_code == 403
    assert _initialize(client, token=new).status_code == 200


def test_agent_submit_can_be_turned_off(client, app_config):
    settings = client.put("/api/mcp/settings", json={"allow_submit": False}).json()
    assert settings["allow_submit"] is False
    assert app_config.mcp.allow_submit is False
    # Changing only allow_submit doesn't turn the server on or mint a token
    assert settings["enabled"] is False and settings["token"] == ""


def test_token_header_works_alongside_a_proxys_basic_auth(client):
    token = client.put("/api/mcp/settings", json={"enabled": True}).json()["token"]
    proxy_auth = {"Authorization": "Basic dXNlcjpwYXNz"}
    assert _initialize(client, extra_headers=proxy_auth).status_code == 403
    response = _initialize(client, extra_headers={**proxy_auth, "X-Achew-Token": token})
    assert response.status_code == 200


def test_no_standing_event_stream(client):
    # A standing GET stream would hold up every server shutdown while an agent is connected
    token = client.put("/api/mcp/settings", json={"enabled": True}).json()["token"]
    response = client.get(MCP_PATH, headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"})
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    # Stateless: no session for the client to keep alive or lose on a restart
    assert "mcp-session-id" not in _initialize(client, token=token).headers
