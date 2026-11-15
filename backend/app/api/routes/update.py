"""In-app updates for native installs started by run.sh or run.bat.

The update itself is app.core.updater. Afterwards the server shuts down, and the run script,
finding the restart file it named in ACHEW_RESTART_FILE, starts over: it reinstalls
dependencies, rebuilds the frontend and launches the new version. Docker, dev.sh and the run
scripts' --debug (auto-reload) mode don't name a restart file, so they can't update in-app.
"""

import asyncio
import logging
import os
import signal
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...core import updater
from .core import get_app_version

logger = logging.getLogger(__name__)

router = APIRouter()

RESTART_FILE_ENV = "ACHEW_RESTART_FILE"

# Set by the Dockerfile. Not a general container check: a native install can run in a container.
DOCKER_ENV = "ACHEW_DOCKER"

# Lets the update response reach the browser before the server starts shutting down.
SHUTDOWN_DELAY_SECONDS = 0.5

# How long a graceful shutdown may take before the process exits anyway. The run script
# restarts Achew either way, since the restart file is already written.
FORCED_EXIT_SECONDS = 20

_update_lock = asyncio.Lock()


def _in_docker_image() -> bool:
    return os.environ.get(DOCKER_ENV) == "1"


def _update_command() -> str:
    return r".\run.bat --update" if sys.platform == "win32" else "./run.sh --update"


@router.get("/update")
async def get_update_status():
    """Whether this install can update itself from the app, and if not, why."""
    version = get_app_version()
    if _in_docker_image():
        return {"install": "docker", "version": version, "can_update": False, "reason": None, "command": None}

    info = await asyncio.to_thread(updater.inspect_install)
    reason, command = info.problem, None
    if reason is None and not os.environ.get(RESTART_FILE_ENV):
        reason = "Achew can only restart itself to finish an update when run.sh or run.bat started it without --debug."
        command = _update_command()
    return {
        "install": info.kind,
        "version": version,
        "can_update": reason is None,
        "reason": reason,
        "command": command,
    }


@router.post("/update")
async def run_update():
    """Updates to the latest version, then restarts Achew through its run script."""
    restart_file = os.environ.get(RESTART_FILE_ENV)
    if _in_docker_image() or not restart_file:
        raise HTTPException(status_code=409, detail="This install can't update itself from the app.")
    if _update_lock.locked():
        raise HTTPException(status_code=409, detail="An update is already in progress.")

    async with _update_lock:
        try:
            result = await asyncio.to_thread(updater.update, log=logger.info)
        except updater.UpdateError as e:
            logger.warning(f"Update failed: {e}")
            raise HTTPException(status_code=409, detail=str(e)) from None

    logger.info(result.describe())
    if result.updated:
        _restart(Path(restart_file))
    return {"updated": result.updated, "version": result.new_version}


def _restart(restart_file: Path) -> None:
    restart_file.parent.mkdir(parents=True, exist_ok=True)
    restart_file.touch()
    logger.info("Restarting Achew to finish the update")
    asyncio.get_running_loop().call_later(SHUTDOWN_DELAY_SECONDS, _shut_down)


def _shut_down() -> None:
    # Shut down the way a stop request from the terminal would
    timer = threading.Timer(FORCED_EXIT_SECONDS, os._exit, args=(0,))
    timer.daemon = True
    timer.start()
    signal.raise_signal(signal.SIGTERM)
