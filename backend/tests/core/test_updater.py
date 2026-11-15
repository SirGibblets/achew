"""Tests for updating a native install (app/core/updater.py).

Archive installs swap in a downloaded release's files and remove files the release dropped,
using the install manifest; these tests build a fake install and release in a temp dir and
stub out the network. Git installs check out the latest release's tag; these tests use a real
local bare repository as the remote, and stub out the latest-release lookup.
"""

import io
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from app.core import updater


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def pyproject(version: str) -> str:
    return f'[project]\nname = "achew"\nversion = "{version}"\n'


def make_release_archive(path: Path, version: str, files: dict[str, str]) -> Path:
    """A GitHub-style source archive: every file under one achew-<version>/ directory."""
    with tarfile.open(path, "w:gz") as tar:
        for rel, text in {"backend/pyproject.toml": pyproject(version), **files}.items():
            data = text.encode()
            info = tarfile.TarInfo(f"achew-{version}/{rel}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


@pytest.fixture
def archive_install(tmp_path):
    """An archive install of 1.0.0 with user settings and an up-to-date manifest."""
    root = tmp_path / "achew"
    files = {
        "backend/pyproject.toml": pyproject("1.0.0"),
        "run.sh": "old run.sh",
        "kept.txt": "same",
        "dropped.txt": "removed in 1.1.0",
        "frontend/src/old/Dropped.svelte": "removed in 1.1.0",
    }
    for rel, text in files.items():
        write(root / rel, text)
    write(root / "backend/app/config/app_config.json", "{}")
    write(root / updater.INSTALL_MANIFEST, "".join(f"{rel}\n" for rel in sorted(files)))
    return root


def serve_release(monkeypatch, archive: Path, tag: str) -> list[str]:
    downloads = []
    monkeypatch.setattr(updater, "latest_release_tag", lambda: tag)

    def fake_download(url, dest):
        downloads.append(url)
        shutil.copy(archive, dest)

    monkeypatch.setattr(updater, "_download", fake_download)
    return downloads


class TestVersions:
    def test_compares_numerically(self):
        assert updater.version_key("v1.10.0") > updater.version_key("1.9.3")
        assert updater.version_key("v1.13.0") == updater.version_key("1.13.0")


class TestArchiveUpdate:
    def test_installs_newer_release_and_removes_dropped_files(self, tmp_path, monkeypatch, archive_install):
        archive = make_release_archive(
            tmp_path / "release.tar.gz", "1.1.0", {"run.sh": "new run.sh", "kept.txt": "same", "added.txt": "new"}
        )
        downloads = serve_release(monkeypatch, archive, "v1.1.0")

        result = updater.update(archive_install, log=lambda _: None)

        assert (result.updated, result.old_version, result.new_version) == (True, "1.0.0", "1.1.0")
        assert downloads == [updater.RELEASE_ARCHIVE_URL.format(tag="v1.1.0")]
        assert (archive_install / "run.sh").read_text() == "new run.sh"
        assert (archive_install / "added.txt").read_text() == "new"
        # Install time, not the archive's (0 here), so uv and Python see the files changed
        assert (archive_install / "backend/pyproject.toml").stat().st_mtime > 0
        assert not (archive_install / "dropped.txt").exists()
        # Directories left empty by dropped files go too
        assert not (archive_install / "frontend").exists()
        # User settings aren't part of a release, so they stay
        assert (archive_install / "backend/app/config/app_config.json").read_text() == "{}"
        manifest = (archive_install / updater.INSTALL_MANIFEST).read_text().splitlines()
        assert manifest == ["added.txt", "backend/pyproject.toml", "kept.txt", "run.sh"]
        assert not (archive_install / ".toolchain/update").exists()

    def test_does_nothing_when_already_on_the_latest_release(self, monkeypatch, archive_install):
        monkeypatch.setattr(updater, "latest_release_tag", lambda: "v1.0.0")
        monkeypatch.setattr(updater, "_download", lambda url, dest: pytest.fail("downloaded"))

        result = updater.update(archive_install, log=lambda _: None)

        assert (result.updated, result.new_version) == (False, "1.0.0")
        assert (archive_install / "dropped.txt").exists()

    def test_never_removes_protected_or_outside_paths_listed_in_the_manifest(self, tmp_path, archive_install):
        outside = tmp_path / "outside.txt"
        outside.write_text("not Achew's")
        manifest = archive_install / updater.INSTALL_MANIFEST
        manifest.write_text("backend/app/config/app_config.json\n../outside.txt\n" + manifest.read_text())
        release = tmp_path / "release"
        write(release / "backend/pyproject.toml", pyproject("1.1.0"))

        updater.install_release_files(archive_install, release)

        assert outside.exists()
        assert (archive_install / "backend/app/config/app_config.json").exists()

    def test_installs_the_version_file_last(self, tmp_path, monkeypatch, archive_install):
        archive = make_release_archive(tmp_path / "release.tar.gz", "1.1.0", {"run.sh": "new run.sh"})
        serve_release(monkeypatch, archive, "v1.1.0")
        real_replace = updater.os.replace

        def failing_replace(src, dst):
            if Path(dst).name == "run.sh":
                raise PermissionError("in use")
            real_replace(src, dst)

        monkeypatch.setattr(updater.os, "replace", failing_replace)

        with pytest.raises(updater.UpdateError, match="stopped partway"):
            updater.update(archive_install, log=lambda _: None)
        # Still reports the old version, so updating again installs the release again
        assert updater.current_version(archive_install) == "1.0.0"

    def test_refuses_archives_with_paths_outside_the_release(self, tmp_path, monkeypatch, archive_install):
        archive = tmp_path / "evil.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo("../../escaped.txt")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        serve_release(monkeypatch, archive, "v1.1.0")

        with pytest.raises(updater.UpdateError, match="Couldn't unpack"):
            updater.update(archive_install, log=lambda _: None)
        assert not (tmp_path / "escaped.txt").exists()


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def publish(upstream: Path, version: str) -> None:
    """Commits a release in the upstream clone, tags it, and pushes both to the remote."""
    write(upstream / "backend/pyproject.toml", pyproject(version))
    write(upstream / "backend/uv.lock", f"lock {version}")
    git(upstream, "add", "-A")
    git(upstream, "commit", "--quiet", "-m", version)
    git(upstream, "tag", f"v{version}")
    git(upstream, "push", "--quiet", "origin", "main", "--tags")


@pytest.fixture
def git_remote(tmp_path):
    """A bare "remote" with release v1.0.0 on main, plus a clone to publish releases from."""
    if shutil.which("git") is None:
        pytest.skip("git isn't installed")
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(remote))
    upstream = tmp_path / "upstream"
    git(tmp_path, "clone", "--quiet", str(remote), str(upstream))
    git(upstream, "checkout", "--quiet", "-b", "main")
    publish(upstream, "1.0.0")
    return remote, upstream


@pytest.fixture
def git_install(tmp_path, git_remote):
    """An install the way the installer makes it: a clone checked out at the latest release's tag."""
    remote, upstream = git_remote
    root = tmp_path / "achew"
    git(tmp_path, "clone", "--quiet", "--branch", "v1.0.0", str(remote), str(root))
    return root, upstream


def latest_release(monkeypatch, tag: str) -> None:
    monkeypatch.setattr(updater, "latest_release_tag", lambda: tag)


class TestGitUpdate:
    def test_checks_out_the_latest_release(self, git_install, monkeypatch):
        root, upstream = git_install
        publish(upstream, "1.1.0")
        latest_release(monkeypatch, "v1.1.0")

        result = updater.update(root, log=lambda _: None)

        assert (result.updated, result.old_version, result.new_version) == (True, "1.0.0", "1.1.0")
        assert git(root, "rev-parse", "HEAD") == git(upstream, "rev-parse", "v1.1.0^{commit}")

    def test_moves_a_branch_checkout_to_the_release_and_keeps_the_branch(self, tmp_path, git_remote, monkeypatch):
        remote, upstream = git_remote
        root = tmp_path / "achew"
        git(tmp_path, "clone", "--quiet", str(remote), str(root))
        branch_head = git(root, "rev-parse", "main")
        publish(upstream, "1.1.0")
        latest_release(monkeypatch, "v1.1.0")

        assert updater.update(root, log=lambda _: None).updated
        assert git(root, "rev-parse", "HEAD") == git(upstream, "rev-parse", "v1.1.0^{commit}")
        assert git(root, "rev-parse", "main") == branch_head

    def test_reports_no_update_when_already_on_the_latest_release(self, git_install, monkeypatch):
        root, _ = git_install
        latest_release(monkeypatch, "v1.0.0")

        result = updater.update(root, log=lambda _: None)

        assert (result.updated, result.new_version) == (False, "1.0.0")

    def test_never_moves_to_an_older_release(self, git_install, monkeypatch):
        root, upstream = git_install
        publish(upstream, "1.1.0")
        latest_release(monkeypatch, "v1.1.0")
        updater.update(root, log=lambda _: None)
        latest_release(monkeypatch, "v1.0.0")

        assert not updater.update(root, log=lambda _: None).updated
        assert updater.current_version(root) == "1.1.0"

    def test_reports_a_release_missing_from_the_remote(self, git_install, monkeypatch):
        root, _ = git_install
        latest_release(monkeypatch, "v9.9.9")

        with pytest.raises(updater.UpdateError, match="isn't in this checkout's origin remote"):
            updater.update(root, log=lambda _: None)

    def test_refuses_local_changes(self, git_install, monkeypatch):
        root, upstream = git_install
        write(root / "backend/pyproject.toml", pyproject("9.9.9"))
        publish(upstream, "1.1.0")
        latest_release(monkeypatch, "v1.1.0")

        assert "local changes" in (updater.inspect_install(root).problem or "")
        with pytest.raises(updater.UpdateError, match="local changes"):
            updater.update(root, log=lambda _: None)

    def test_discards_rewritten_lockfiles_instead_of_blocking(self, git_install, monkeypatch):
        root, upstream = git_install
        write(root / "backend/uv.lock", "relocked by an older uv")
        publish(upstream, "1.1.0")
        latest_release(monkeypatch, "v1.1.0")

        assert updater.inspect_install(root).problem is None
        assert updater.update(root, log=lambda _: None).updated
        assert (root / "backend/uv.lock").read_text() == "lock 1.1.0"

    def test_untracked_files_dont_block_updates(self, git_install, monkeypatch):
        root, upstream = git_install
        write(root / "backend/app/config/app_config.json", "{}")
        publish(upstream, "1.1.0")
        latest_release(monkeypatch, "v1.1.0")

        assert updater.update(root, log=lambda _: None).updated
        assert (root / "backend/app/config/app_config.json").read_text() == "{}"
