"""Settings for agent access through the built-in MCP server (Settings → Agent Access)."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.config import get_app_config, update_app_config
from ...mcp_server import MCP_PATH, generate_token

logger = logging.getLogger(__name__)

router = APIRouter()


class MCPSettingsResponse(BaseModel):
    enabled: bool
    allow_submit: bool
    # The browser already has unauthenticated access to the whole API, so showing it the
    # token gives nothing away; the UI needs it for the connection instructions.
    token: str
    path: str


class MCPSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    allow_submit: Optional[bool] = None


def _response() -> MCPSettingsResponse:
    mcp = get_app_config().mcp
    return MCPSettingsResponse(enabled=mcp.enabled, allow_submit=mcp.allow_submit, token=mcp.token, path=MCP_PATH)


def _save() -> None:
    if not update_app_config(get_app_config()):
        raise HTTPException(status_code=500, detail="Failed to save agent access settings")


@router.get("/mcp/settings", response_model=MCPSettingsResponse)
async def get_mcp_settings():
    """Get agent access settings"""
    return _response()


@router.put("/mcp/settings", response_model=MCPSettingsResponse)
async def update_mcp_settings(request: MCPSettingsUpdate):
    """Turn agent access on or off, or change whether agents may submit. Turning it on the
    first time generates the access token."""
    mcp = get_app_config().mcp
    if request.enabled is not None:
        mcp.enabled = request.enabled
        if mcp.enabled and not mcp.token:
            mcp.token = generate_token()
        logger.info(f"Agent access (MCP) turned {'on' if mcp.enabled else 'off'}")
    if request.allow_submit is not None:
        mcp.allow_submit = request.allow_submit
    _save()
    return _response()


@router.post("/mcp/settings/token", response_model=MCPSettingsResponse)
async def regenerate_mcp_token():
    """Replace the access token; agents using the old one are locked out"""
    get_app_config().mcp.token = generate_token()
    _save()
    logger.info("Agent access (MCP) token regenerated")
    return _response()
