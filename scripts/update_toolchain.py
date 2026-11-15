"""Bump the uv / Node.js / Python versions pinned in toolchain.env.

Checksums come from each release's published sums file, so the run scripts can verify
what they download against values committed to the repo.

Usage, from the repo root:

    uv run --no-project scripts/update_toolchain.py --uv latest --node 24
    uv run --no-project scripts/update_toolchain.py --uv 0.11.21 --node 24.22.2 --python 3.12

--uv takes a version or "latest"; --node takes a version or a major version, which resolves
to that line's newest release.
"""

import argparse
import json
import re
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / "toolchain.env"

# The archives toolchain.sh / toolchain.ps1 download, keyed by their checksum variable.
UV_ARCHIVES = {
    "UV_SHA256_aarch64_apple_darwin": "uv-aarch64-apple-darwin.tar.gz",
    "UV_SHA256_x86_64_apple_darwin": "uv-x86_64-apple-darwin.tar.gz",
    "UV_SHA256_aarch64_unknown_linux_musl": "uv-aarch64-unknown-linux-musl.tar.gz",
    "UV_SHA256_x86_64_unknown_linux_musl": "uv-x86_64-unknown-linux-musl.tar.gz",
    "UV_SHA256_aarch64_pc_windows_msvc": "uv-aarch64-pc-windows-msvc.zip",
    "UV_SHA256_x86_64_pc_windows_msvc": "uv-x86_64-pc-windows-msvc.zip",
}
NODE_ARCHIVES = {
    "NODE_SHA256_darwin_arm64": "darwin-arm64.tar.gz",
    "NODE_SHA256_darwin_x64": "darwin-x64.tar.gz",
    "NODE_SHA256_linux_arm64": "linux-arm64.tar.gz",
    "NODE_SHA256_linux_x64": "linux-x64.tar.gz",
    "NODE_SHA256_win_arm64": "win-arm64.zip",
    "NODE_SHA256_win_x64": "win-x64.zip",
}


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode()


def parse_sums(text: str) -> dict[str, str]:
    """Maps file name to SHA-256 for `<hash>  <name>` lines (uv marks names with '*')."""
    sums = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    return sums


def uv_pins(spec: str) -> dict[str, str]:
    version = spec
    if spec == "latest":
        release = json.loads(
            fetch("https://api.github.com/repos/astral-sh/uv/releases/latest")
        )
        version = release["tag_name"]
    sums = parse_sums(
        fetch(f"https://github.com/astral-sh/uv/releases/download/{version}/sha256.sum")
    )
    return {"UV_VERSION": version} | {
        key: sums[name] for key, name in UV_ARCHIVES.items()
    }


def node_pins(spec: str) -> dict[str, str]:
    version = spec
    if spec.isdigit():
        releases = json.loads(fetch("https://nodejs.org/dist/index.json"))
        version = next(
            r["version"] for r in releases if r["version"].startswith(f"v{spec}.")
        )
    version = version.removeprefix("v")
    sums = parse_sums(fetch(f"https://nodejs.org/dist/v{version}/SHASUMS256.txt"))
    return {"NODE_VERSION": version} | {
        key: sums[f"node-v{version}-{suffix}"] for key, suffix in NODE_ARCHIVES.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--uv", help='uv version, or "latest"')
    parser.add_argument(
        "--node", help="Node.js version, or a major version for its newest release"
    )
    parser.add_argument("--python", help="Python version uv should install, e.g. 3.12")
    args = parser.parse_args()

    pins: dict[str, str] = {}
    if args.uv:
        pins |= uv_pins(args.uv)
    if args.node:
        pins |= node_pins(args.node)
    if args.python:
        pins["PYTHON_VERSION"] = args.python
    if not pins:
        parser.error("nothing to update")

    text = ENV_FILE.read_text()
    for key, value in pins.items():
        text, count = re.subn(
            rf"^{key}=.*$", f"{key}={value}", text, flags=re.MULTILINE
        )
        if count != 1:
            raise SystemExit(
                f"{key} appears {count} times in {ENV_FILE.name}, expected once"
            )
    ENV_FILE.write_text(text)
    print(
        f"Updated {ENV_FILE.name}: "
        + ", ".join(
            f"{k}={v}"
            for k, v in pins.items()
            if not k.startswith(("UV_SHA", "NODE_SHA"))
        )
    )


if __name__ == "__main__":
    main()
