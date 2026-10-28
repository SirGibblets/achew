"""Locate the ffmpeg binary Achew runs.

Achew ships its own ffmpeg through the achew-ffmpeg wheel: a lean LGPL build that
includes libfdk_aac, the only FFmpeg decoder that handles xHE-AAC (USAC) speech
frames. Every Achew ffmpeg call goes through ffmpeg_path(), and put_ffmpeg_on_path()
makes libraries that run `ffmpeg` by name (mlx-whisper, parakeet-mlx, pywhispercpp)
use the same binary.

`python -m app.core.ffmpeg` checks that the ffmpeg Achew resolves actually runs; the
run scripts call it so a platform without a bundled build fails at startup with
instructions, not partway through a workflow.
"""

import functools
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# Environment variable users can set to run a different ffmpeg (troubleshooting, or
# platforms achew-ffmpeg has no wheel for). Without libfdk_aac, xHE-AAC books are
# flagged as unsupported.
FFMPEG_ENV_VAR = "ACHEW_FFMPEG"

_FFMPEG_EXE = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


@functools.lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    """Return the ffmpeg binary to run: ACHEW_FFMPEG, else the bundled build, else PATH."""
    override = os.environ.get(FFMPEG_ENV_VAR)
    if override:
        return override
    try:
        import achew_ffmpeg

        return achew_ffmpeg.ffmpeg_path()
    except (ImportError, FileNotFoundError) as e:
        logger.warning(f"Bundled ffmpeg unavailable ({e}); falling back to ffmpeg on PATH")
    # A bare name still lets subprocess raise a clear FileNotFoundError if it's missing
    return shutil.which("ffmpeg") or "ffmpeg"


@functools.lru_cache(maxsize=1)
def ffmpeg_version() -> str:
    """Return the first line of `ffmpeg -version` (e.g. "ffmpeg version 6.1.1 …"),
    or an empty string if ffmpeg couldn't be run."""
    try:
        result = subprocess.run(
            [ffmpeg_path(), "-version"],
            capture_output=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning(f"Failed to get ffmpeg version: {e}")
        return ""
    lines = result.stdout.splitlines() if result.returncode == 0 else []
    return lines[0].strip() if lines else ""


@functools.lru_cache(maxsize=1)
def supports_xhe_aac() -> bool:
    """Whether the ffmpeg in use has the libfdk_aac decoder, which xHE-AAC needs."""
    try:
        result = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-decoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning(f"Failed to list ffmpeg decoders: {e}")
        return False
    return " libfdk_aac " in result.stdout


def put_ffmpeg_on_path() -> None:
    """Make `ffmpeg` on PATH resolve to ffmpeg_path(), for libraries that run it by name.

    Nothing else on PATH may move ahead of where it was: ACHEW_FFMPEG can point into a
    shared directory like /usr/bin, and prepending that would shadow the venv's python
    and every other tool. So only the interpreter's own scripts directory (where the
    bundled build installs into a venv) is prepended directly, as venv activation would;
    any other binary is exposed through a directory holding nothing but an `ffmpeg`
    link to it, which also covers binaries not named ffmpeg."""
    target = shutil.which(ffmpeg_path())
    if not target:
        return
    target = os.path.abspath(target)
    current = shutil.which("ffmpeg")
    if current and _same_file(current, target):
        return
    directory = os.path.dirname(target)
    if not (os.path.basename(target) == _FFMPEG_EXE and _same_file(directory, sysconfig.get_path("scripts"))):
        directory = _link_directory(target)
        if directory is None:
            return
    entries = [e for e in os.environ.get("PATH", "").split(os.pathsep) if e and not _same_file(e, directory)]
    os.environ["PATH"] = os.pathsep.join([directory, *entries])


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _link_directory(target: str) -> Optional[str]:
    """A directory holding only an `ffmpeg` link (or copy) to target, or None if it can't
    be made. It lives with Achew's other temp files and is named after the target, so
    restarts reuse it and different targets never collide."""
    digest = hashlib.sha256(target.encode("utf-8", "surrogateescape")).hexdigest()[:12]
    directory = os.path.join(tempfile.gettempdir(), "achew", f"ffmpeg-link-{digest}")
    link = os.path.join(directory, _FFMPEG_EXE)
    if _same_file(link, target):
        return directory
    # Build next to the final name, then swap it in, so a concurrent start never sees
    # a missing ffmpeg
    staging = f"{link}.{os.getpid()}.tmp"
    try:
        os.makedirs(directory, exist_ok=True)
        try:
            os.symlink(target, staging)
        except OSError:
            # Windows needs a privilege for symlinks; a hard link or a copy works too
            try:
                os.link(target, staging)
            except OSError:
                shutil.copy2(target, staging)
        os.replace(staging, link)
    except OSError as e:
        logger.warning(f"Couldn't expose {target} as `ffmpeg` on PATH ({e}); ASR libraries may use another ffmpeg")
        try:
            os.remove(staging)
        except OSError:
            pass
        return None
    return directory


if __name__ == "__main__":
    version = ffmpeg_version()
    if not version:
        print(
            f"ffmpeg not found or not runnable: {ffmpeg_path()}\n"
            "Achew installs its own ffmpeg on Linux (x86_64, arm64), macOS and Windows (x64).\n"
            "On other platforms, install ffmpeg (https://ffmpeg.org/download.html) or set "
            f"{FFMPEG_ENV_VAR} to the path of an ffmpeg binary.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Using {ffmpeg_path()} ({version})")
