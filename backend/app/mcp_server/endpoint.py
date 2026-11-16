"""The /mcp HTTP endpoint: Achew's MCP server over Streamable HTTP, inside the FastAPI app.

It's off until the user turns it on (Settings → Agent Access), and every request must carry
the bearer token shown there. Achew's REST API has no authentication of its own, but the
token keeps a web page the user visits from reaching /mcp through DNS rebinding, and keeps
other machines on the network out when Achew listens on 0.0.0.0 (the Docker default). Both
settings are read per request, so turning access off or regenerating the token takes effect
at once.
"""

import hmac
import json
import logging
import secrets
import signal
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import Headers
from starlette.types import Receive, Scope, Send

from app.core.config import get_app_config

from .runtime import shutdown

logger = logging.getLogger(__name__)

MCP_PATH = "/mcp"

# Alternative to "Authorization: Bearer <token>", for when a reverse proxy in front of Achew
# already uses the Authorization header for its own (basic) auth
TOKEN_HEADER = "x-achew-token"

# Bytes of randomness in a generated token (URL-safe base64, so ~43 characters)
TOKEN_BYTES = 32


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


async def _send_json(send: Send, status: int, payload: dict, headers: Optional[List[tuple]] = None) -> None:
    body = json.dumps(payload).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *(headers or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _watch_for_shutdown() -> None:
    """Chain onto the server's SIGINT/SIGTERM handlers to flag a shutdown as soon as it starts.

    uvicorn installs its handlers with signal.signal before the app starts and restores them
    when it stops, so wrapping them here needs no cleanup. Signals only reach the main thread;
    elsewhere (tests) there's nothing to watch.
    """
    if threading.current_thread() is not threading.main_thread():
        return
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous = signal.getsignal(sig)
        if not callable(previous):
            continue

        def handler(signum, frame, previous=previous):
            shutdown.started = True
            previous(signum, frame)

        signal.signal(sig, handler)


def _has_token(headers: Headers, token: str) -> bool:
    scheme, _, bearer = headers.get("authorization", "").partition(" ")
    candidates = [headers.get(TOKEN_HEADER, "")]
    if scheme.lower() == "bearer":
        candidates.append(bearer)
    return any(c and hmac.compare_digest(c.strip().encode(), token.encode()) for c in candidates)


class MCPEndpoint:
    """ASGI app for /mcp: checks that access is on and the token matches, then hands the
    request to the MCP SDK's Streamable HTTP transport."""

    def __init__(self, server: MCPServer):
        self.server = server

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None, None]:
        """Run the transport's session manager for the app's lifetime. A fresh one per run,
        since a session manager can only run once."""
        shutdown.started = False
        _watch_for_shutdown()
        self.server.streamable_http_app(
            streamable_http_path=MCP_PATH,
            # Stateless, and GET answered with 405 in __call__: every response ends with its request,
            # and no session or standing event stream outlives it. The server waits for open
            # connections to close before it shuts the app down, and a standing stream (which
            # Claude Code opens) only closes when the app does, so it would hang every restart while
            # an agent is connected. Stateless also lets agents carry on across restarts without
            # reconnecting. All state lives in the app, not the MCP session, and no tool needs to
            # call back to the client.
            stateless_http=True,
            # Host/Origin checks would reject Docker and LAN setups; the token does that job here
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        async with self.server.session_manager.run():
            yield

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return

        config = get_app_config().mcp
        if not config.enabled:
            await _send_json(
                send,
                404,
                {"error": "Achew's MCP server is turned off. Turn it on in Achew under Settings → Agent Access."},
            )
            return

        if not config.token or not _has_token(Headers(scope=scope), config.token):
            # 403 rather than 401: a 401 sends MCP clients off looking for an OAuth server
            logger.warning("Rejected an MCP request with a missing or wrong token")
            await _send_json(
                send,
                403,
                {
                    "error": "Missing or wrong token. Copy the connection settings from Achew under "
                    "Settings → Agent Access (the token changes when it's regenerated)."
                },
            )
            return

        if scope["method"] == "GET":
            # No standing event stream (the MCP spec's 405): it would outlive every request and
            # hold up shutdown (see lifespan), and nothing here sends messages outside a request
            await _send_json(
                send, 405, {"error": "Achew doesn't offer a standing event stream"}, headers=[(b"allow", b"POST")]
            )
            return

        await self.server.session_manager.handle_request(scope, receive, send)
