"""Updates a native (non-Docker) Achew install to the latest release.

Either way, "latest" is GitHub's latest release, and an install only ever moves to a newer one:

- A git checkout (cloned by the installer, which checks out the latest release's tag, or by
  hand) fetches tags and checks out the new release's tag. A checkout on a branch, such as one
  that followed main before Achew updated itself, moves to the release too; the branch stays.
- Anything else (the installer without git, or an extracted release archive) downloads the
  release and swaps in its files. The files each release installed are listed in
  INSTALL_MANIFEST, so files that a newer release drops are removed instead of left behind.

Standard library only: run.sh / run.bat run this file directly for --update, before the
backend's dependencies are installed, and the backend imports it for in-app updates.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

ROOT = Path(__file__).resolve().parents[3]

# Where releases come from. Overridable for forks, or a local server in tests ({tag} is the
# release's git tag). install.sh and install.ps1 read the same variables.
LATEST_RELEASE_URL = os.environ.get(
    "ACHEW_LATEST_RELEASE_URL", "https://api.github.com/repos/SirGibblets/achew/releases/latest"
)
RELEASE_ARCHIVE_URL = os.environ.get(
    "ACHEW_RELEASE_ARCHIVE_URL", "https://github.com/SirGibblets/achew/archive/refs/tags/{tag}.tar.gz"
)

# The files the installed release put in an archive install, one relative path per line.
INSTALL_MANIFEST = ".toolchain/install-manifest.txt"

# Never removed when a release drops files: user data, local tools and build output.
PROTECTED_DIRS = (
    ".git",
    ".toolchain",
    "backend/.venv",
    "backend/app/config",
    "frontend/node_modules",
    "frontend/dist",
    "config",
    "cache",
)

# Installed last, so an update interrupted partway still reports the old version and a retry
# installs everything again.
VERSION_FILE = "backend/pyproject.toml"

# Never let git stop to ask for credentials: nobody is there to answer during an in-app update.
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

# Generated files that installing dependencies can rewrite (older uv and npm versions did, on
# users' machines). A git checkout's changes to these are discarded instead of blocking updates.
LOCKFILES = ("backend/uv.lock", "frontend/package-lock.json")


class UpdateError(Exception):
    """An update that can't go ahead. The message is shown to the user as is."""


@dataclass
class InstallInfo:
    kind: Literal["git", "archive"]
    version: str
    # Why this install can't update itself, or None if it can
    problem: str | None = None


@dataclass
class UpdateResult:
    updated: bool
    old_version: str
    new_version: str

    def describe(self) -> str:
        if not self.updated:
            return f"Achew is up to date (v{self.old_version})."
        if self.new_version == self.old_version:
            return f"Updated Achew (v{self.new_version})."
        return f"Updated Achew from v{self.old_version} to v{self.new_version}."


def current_version(root: Path = ROOT) -> str:
    with open(root / VERSION_FILE, "rb") as f:
        return tomllib.load(f)["project"]["version"]


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def inspect_install(root: Path = ROOT) -> InstallInfo:
    version = current_version(root)
    if not (root / ".git").exists():
        return InstallInfo("archive", version)
    return InstallInfo("git", version, _git_problem(root))


def update(root: Path = ROOT, log: Callable[[str], None] = print) -> UpdateResult:
    info = inspect_install(root)
    if info.problem:
        raise UpdateError(info.problem)
    if info.kind == "git":
        return _update_git(root, info, log)
    return _update_archive(root, info, log)


def _git(root: Path, *args: str, timeout: float = 300) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, env=GIT_ENV, capture_output=True, text=True, check=True, timeout=timeout
        )
    except FileNotFoundError:
        raise UpdateError("This install is a git checkout, but git isn't installed.") from None
    except subprocess.TimeoutExpired:
        raise UpdateError(f"git {args[0]} timed out.") from None
    except subprocess.CalledProcessError as e:
        raise UpdateError(f"git {args[0]} failed: {(e.stderr or e.stdout).strip()}") from None
    # Not strip(): `status --porcelain` lines can start with a space
    return result.stdout.rstrip()


def _changed_files(root: Path) -> list[str]:
    """Tracked files with uncommitted changes."""
    output = _git(root, "status", "--porcelain", "--untracked-files=no", "--no-renames")
    return [line[3:] for line in output.splitlines()]


def _git_problem(root: Path) -> str | None:
    if shutil.which("git") is None:
        return "This install is a git checkout, but git isn't installed."
    if any(path not in LOCKFILES for path in _changed_files(root)):
        return "This git checkout has local changes. Commit or discard them, then update again."
    return None


def _update_git(root: Path, info: InstallInfo, log: Callable[[str], None]) -> UpdateResult:
    tag = latest_release_tag()
    if version_key(tag) <= version_key(info.version):
        return UpdateResult(False, info.version, info.version)

    log(f"Fetching Achew {tag}...")
    _git(root, "fetch", "--quiet", "--tags", "origin")
    try:
        _git(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}")
    except UpdateError:
        raise UpdateError(f"The {tag} release isn't in this checkout's origin remote.") from None

    if lockfiles := [path for path in _changed_files(root) if path in LOCKFILES]:
        log(f"Discarding local changes to {', '.join(lockfiles)}")
        _git(root, "checkout", "--", *lockfiles)
    try:
        branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    except UpdateError:
        # Not on a branch: on a release already, or some other commit
        branch = None
    if branch:
        log(f"Switching from the {branch} branch to the {tag} release (the branch is kept)")
    _git(root, "checkout", "--quiet", f"refs/tags/{tag}")
    return UpdateResult(True, info.version, current_version(root))


def latest_release_tag() -> str:
    request = urllib.request.Request(
        LATEST_RELEASE_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "achew-updater"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)["tag_name"]
    except (OSError, ValueError, KeyError) as e:
        raise UpdateError(f"Couldn't look up the latest Achew release: {e}") from None


def _download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "achew-updater"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(dest, "wb") as f:
            shutil.copyfileobj(response, f)
    except OSError as e:
        raise UpdateError(f"Couldn't download {url}: {e}") from None


def _update_archive(root: Path, info: InstallInfo, log: Callable[[str], None]) -> UpdateResult:
    tag = latest_release_tag()
    if version_key(tag) <= version_key(info.version):
        return UpdateResult(False, info.version, info.version)
    # The "data" filter refuses archive members that would land outside the target directory
    if not hasattr(tarfile, "data_filter"):
        raise UpdateError("Updating needs Python 3.11.4 or newer.")

    staging = root / ".toolchain" / "update"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        log(f"Downloading Achew {tag}...")
        archive = staging / "release.tar.gz"
        _download(RELEASE_ARCHIVE_URL.format(tag=tag), archive)
        try:
            with tarfile.open(archive) as tar:
                tar.extractall(staging / "release", filter="data")
        except (tarfile.TarError, OSError) as e:
            raise UpdateError(f"Couldn't unpack the {tag} release: {e}") from None
        entries = list((staging / "release").iterdir())
        release = entries[0] if len(entries) == 1 else None
        if release is None or not (release / VERSION_FILE).is_file():
            raise UpdateError(f"The {tag} release download doesn't contain Achew.")
        log(f"Installing Achew {tag}...")
        try:
            install_release_files(root, release)
        except OSError as e:
            raise UpdateError(
                f"The update stopped partway ({e}). Close anything using Achew's files and update again."
            ) from None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return UpdateResult(True, info.version, current_version(root))


def install_release_files(root: Path, release: Path) -> None:
    """Moves an extracted release's files into root and removes files it no longer has."""
    new_files = sorted(p.relative_to(release).as_posix() for p in release.rglob("*") if p.is_file())
    for rel in sorted(new_files, key=lambda rel: rel == VERSION_FILE):
        dest = root / rel
        # A path that changed between a file and a directory since the old release
        if dest.is_dir():
            shutil.rmtree(dest)
        if dest.parent.is_file():
            dest.parent.unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(release / rel, dest)
        # Stamped with the install time, as git checkouts are. Archive files keep the release
        # commit's time, and uv (rebuilding the app's metadata) and Python's bytecode cache use
        # mtimes to tell whether a file changed.
        os.utime(dest)

    manifest = root / INSTALL_MANIFEST
    old_files = set(manifest.read_text().splitlines()) if manifest.is_file() else set()
    for rel in sorted(old_files - set(new_files)):
        _remove_stale(root, rel)

    manifest.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest.with_name(manifest.name + ".tmp")
    tmp.write_text("".join(f"{rel}\n" for rel in new_files))
    os.replace(tmp, manifest)


def _remove_stale(root: Path, rel: str) -> None:
    parts = Path(rel).parts
    if not rel or Path(rel).is_absolute() or ".." in parts:
        return
    if any(rel == d or rel.startswith(f"{d}/") for d in PROTECTED_DIRS):
        return
    path = root / rel
    if path.is_file():
        path.unlink()
    # Remove directories the release no longer uses, once nothing else is in them
    parent = path.parent
    while parent != root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def main() -> int:
    try:
        result = update(log=lambda message: print(message, flush=True))
    except UpdateError as e:
        print(e, file=sys.stderr)
        return 1
    print(result.describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())
