#!/usr/bin/env python3
"""Validate links to the docs site against files under docs/.

Scans frontend/src for both ``<DocLink path="...">`` usages and raw
``https://achew.readthedocs.io/...`` URLs, resolves each to a markdown file
(``docs/{path}.md`` or ``docs/{path}/index.md``), and verifies that any
``#anchor`` fragment matches a heading slug in that file.

Run from repo root:

    python3 checks/validate_doc_links.py

Exits non-zero if any link is broken.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
DOCS_ROOT = REPO_ROOT / "docs"
DOCLINK_FILE = FRONTEND_SRC / "components" / "DocLink.svelte"

DOCLINK_RE = re.compile(r"<DocLink\b([^>]*?)/?>", re.DOTALL)
PATH_ATTR_RE = re.compile(r'\bpath\s*=\s*"([^"]+)"')
RAW_URL_RE = re.compile(r'https?://achew\.readthedocs\.io(/[^\s"\'<>)\]]*)?')
RAW_URL_EXTS = ("*.svelte", "*.js")


@dataclass
class Usage:
    file: Path
    line: int
    path: str
    source: str  # "DocLink" or "raw URL"
    raw: str  # original link text, for error messages


def find_doclink_usages() -> list[Usage]:
    usages: list[Usage] = []
    for svelte in FRONTEND_SRC.rglob("*.svelte"):
        text = svelte.read_text(encoding="utf-8")
        for match in DOCLINK_RE.finditer(text):
            attrs = match.group(1)
            path_match = PATH_ATTR_RE.search(attrs)
            if not path_match:
                continue
            line = text.count("\n", 0, match.start()) + 1
            path = path_match.group(1)
            usages.append(Usage(file=svelte, line=line, path=path, source="DocLink", raw=path))
    return usages


def url_to_doc_path(url_path: str) -> str:
    """Convert a readthedocs URL path to a DocLink-style path.

    ``/stable/foo/bar/`` → ``/foo/bar/``; ``/stable/`` or ``/stable`` → ``/``.
    The first segment (version) is dropped — we don't validate which version
    was linked, only that the underlying doc exists.
    """
    stripped = url_path.lstrip("/")
    if not stripped:
        return "/"
    parts = stripped.split("/", 1)
    rest = parts[1] if len(parts) > 1 else ""
    return "/" + rest


def find_raw_url_usages() -> list[Usage]:
    usages: list[Usage] = []
    files: list[Path] = []
    for pattern in RAW_URL_EXTS:
        files.extend(FRONTEND_SRC.rglob(pattern))
    files.extend(REPO_ROOT.glob("*.md"))
    for path in files:
        if path.resolve() == DOCLINK_FILE.resolve():
            continue  # contains the BASE_URL constant, not a real link
        text = path.read_text(encoding="utf-8")
        for match in RAW_URL_RE.finditer(text):
            url = match.group(0)
            url_path = match.group(1) or ""
            doc_path = url_to_doc_path(url_path)
            line = text.count("\n", 0, match.start()) + 1
            usages.append(Usage(file=path, line=line, path=doc_path, source="raw URL", raw=url))
    return usages


def resolve_doc_file(path: str) -> Path | None:
    """Map a DocLink path (e.g. ``/getting-started/foo/``) to a docs/*.md file."""
    clean = path.split("#", 1)[0].split("?", 1)[0].strip("/")
    candidates = [DOCS_ROOT / f"{clean}.md"] if clean else []
    candidates.append(DOCS_ROOT / clean / "index.md")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
_ATTR_LIST_ID_RE = re.compile(r"\{[^}]*#([\w-]+)[^}]*\}\s*$")


def slugify(text: str) -> str:
    """Approximate the slug zensical assigns to a heading."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def collect_anchors(md_file: Path) -> set[str]:
    anchors: set[str] = set()
    text = md_file.read_text(encoding="utf-8")
    # Strip fenced code blocks so headings inside them don't count.
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    seen: dict[str, int] = {}
    for match in _HEADING_RE.finditer(text):
        heading = match.group(2).strip()
        attr_match = _ATTR_LIST_ID_RE.search(heading)
        if attr_match:
            anchors.add(attr_match.group(1))
            heading = _ATTR_LIST_ID_RE.sub("", heading).strip()
        slug = slugify(heading)
        if not slug:
            continue
        count = seen.get(slug, 0)
        anchors.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    # Inline HTML anchors: <a id="foo"> or <a name="foo">
    for match in re.finditer(r'<a\s+(?:id|name)\s*=\s*"([^"]+)"', text):
        anchors.add(match.group(1))
    return anchors


def main() -> int:
    if not DOCS_ROOT.is_dir():
        print(f"docs/ not found at {DOCS_ROOT}", file=sys.stderr)
        return 2
    if not FRONTEND_SRC.is_dir():
        print(f"frontend/src not found at {FRONTEND_SRC}", file=sys.stderr)
        return 2

    usages = find_doclink_usages() + find_raw_url_usages()
    if not usages:
        print("No doc links found.")
        return 0

    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}

    for usage in usages:
        rel = usage.file.relative_to(REPO_ROOT)
        location = f"{rel}:{usage.line}"
        target = resolve_doc_file(usage.path)
        if target is None:
            errors.append(f"{location}: missing doc for {usage.source} {usage.raw!r}")
            continue
        fragment = usage.path.split("#", 1)[1] if "#" in usage.path else ""
        if fragment:
            anchors = anchor_cache.setdefault(target, collect_anchors(target))
            if fragment not in anchors:
                doc_rel = target.relative_to(REPO_ROOT)
                errors.append(
                    f"{location}: missing anchor #{fragment} in {doc_rel} "
                    f"({usage.source} {usage.raw!r})"
                )

    print(f"Checked {len(usages)} doc link(s).")
    if errors:
        print(f"\n{len(errors)} broken link(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("All doc links resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
