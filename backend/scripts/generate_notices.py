#!/usr/bin/env python3
"""Generate a third-party license notices file for the installed Python deps.

The Achew Docker image bundles every backend dependency, so the permissive
licenses (MIT/BSD/ISC/Apache) require their copyright + license text to travel
with that image. This walks a site-packages directory, reads each distribution's
metadata and bundled license text, and writes one combined notices document.

Usage (run against the image's venv during the Docker build):

    python scripts/generate_notices.py \
        --site .venv/lib/python3.11/site-packages \
        --title "Achew — Python dependencies" \
        --prepend frontend-notices.txt \
        --output THIRD_PARTY_NOTICES.txt
"""

from __future__ import annotations

import argparse
import sysconfig
from pathlib import Path

# License/notice files are stored either directly in the .dist-info directory or
# (newer wheels) under a licenses/ subdirectory. Globs use leading wildcards so
# prefixed names like CLI-LICENSE.md (the proprietary Copilot CLI license) and
# MIT-LICENSE.txt are caught, not just files that start with "LICENSE".
_LICENSE_GLOBS = ("*LICENSE*", "*LICENCE*", "*COPYING*", "*NOTICE*", "AUTHORS*")

_SEP = "\n" + "=" * 80 + "\n"


def _read_metadata(metadata_path: Path) -> dict[str, list[str]]:
    """Parse the RFC822-style METADATA headers we care about (multi-valued)."""
    fields: dict[str, list[str]] = {}
    if not metadata_path.is_file():
        return fields
    for line in metadata_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line[0] in " \t":
            continue
        if line.startswith(("Name:", "Version:", "License:", "License-Expression:", "Classifier:", "License-File:")):
            key, _, value = line.partition(":")
            fields.setdefault(key.strip(), []).append(value.strip())
        elif not line.strip():
            break  # end of headers
    return fields


def _license_summary(fields: dict[str, list[str]]) -> str:
    if fields.get("License-Expression"):
        return fields["License-Expression"][0]
    classifiers = [c.split("::")[-1].strip() for c in fields.get("Classifier", []) if "License ::" in c]
    if classifiers:
        return "; ".join(classifiers)
    lic = (fields.get("License") or [""])[0]
    # Some packages dump the whole license body into the License field; keep one line.
    return lic.splitlines()[0] if lic else "See license text below"


def _license_texts(info_dir: Path, license_files: list[str]) -> list[tuple[str, str]]:
    bases = (info_dir, info_dir / "licenses")
    seen: dict[str, str] = {}

    def add(path: Path) -> None:
        if path.is_file() and path.name not in seen:
            seen[path.name] = path.read_text(encoding="utf-8", errors="replace").rstrip()

    # License-File metadata entries are authoritative (they list e.g. both the
    # MIT LICENSE and the proprietary CLI-LICENSE.md for github-copilot-sdk).
    for rel in license_files:
        for base in bases:
            add(base / Path(rel).name)
    # Supplement with anything else license-shaped the wheel shipped.
    for base in bases:
        if base.is_dir():
            for pattern in _LICENSE_GLOBS:
                for path in sorted(base.glob(pattern)):
                    add(path)
    return list(seen.items())


def _render_python(site: Path) -> str:
    blocks: list[str] = []
    for info_dir in sorted(site.glob("*.dist-info"), key=lambda p: p.name.lower()):
        fields = _read_metadata(info_dir / "METADATA")
        name = (fields.get("Name") or [info_dir.name])[0]
        version = (fields.get("Version") or ["?"])[0]
        texts = _license_texts(info_dir, fields.get("License-File", []))
        header = f"{name} {version}\nLicense: {_license_summary(fields)}"
        if texts:
            body = "\n\n".join(f"--- {fname} ---\n{text}" for fname, text in texts)
            blocks.append(f"{header}\n\n{body}")
        else:
            blocks.append(f"{header}\n\n(No license text file was bundled with this distribution.)")
    return _SEP.join(blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site",
        type=Path,
        default=Path(sysconfig.get_path("purelib")),
        help="site-packages directory to scan (default: the active venv's, so `uv run` targets it)",
    )
    parser.add_argument("--title", default="Python dependencies")
    parser.add_argument("--prepend", type=Path, help="a pre-generated notices file (e.g. frontend) to place first")
    parser.add_argument("--output", type=Path, help="output file (defaults to stdout)")
    args = parser.parse_args()

    if not args.site.is_dir():
        parser.error(f"site-packages not found: {args.site}")

    parts: list[str] = []
    if args.prepend and args.prepend.is_file():
        parts.append(args.prepend.read_text(encoding="utf-8", errors="replace").rstrip())
    parts.append(f"{'#' * 80}\n# {args.title}\n{'#' * 80}\n\n" + _render_python(args.site))

    document = (_SEP.join(parts)).rstrip() + "\n"
    if args.output:
        args.output.write_text(document, encoding="utf-8")
        print(f"Wrote {args.output} ({len(document):,} bytes)")
    else:
        print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
