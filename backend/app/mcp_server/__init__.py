"""Achew's MCP server, so agents can run workflows and edit chapters (see server.py)."""

from .endpoint import MCP_PATH, MCPEndpoint, generate_token
from .server import create_mcp_server

__all__ = ["MCP_PATH", "MCPEndpoint", "create_mcp_server", "generate_token"]
