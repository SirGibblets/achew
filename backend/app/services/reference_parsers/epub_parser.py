import logging
import posixpath
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from ...models.references import TitleReference, TitleRefType
from .base_parser import BaseTitleRefParser

logger = logging.getLogger(__name__)

# Path to the container descriptor that every EPUB (2 and 3) must ship; it
# points at the package (OPF) document, which in turn locates the TOC.
_CONTAINER_PATH = "META-INF/container.xml"

# Manifest media type of the EPUB 2 NCX navigation document.
_NCX_MEDIA_TYPE = "application/x-dtbncx+xml"

# Manifest media types treated as spine/content documents for the
# filename-based fallback when no TOC titles can be extracted.
_DOCUMENT_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}


def _localname(tag: str) -> str:
    """Strip the ``{namespace}`` prefix ElementTree prepends, lowercased.

    EPUB files vary in whether (and how) they declare the OPF/NCX namespaces, so
    matching on the bare local name keeps parsing resilient to those quirks.
    """
    return tag.rsplit("}", 1)[-1].lower()


def _norm(text: str | None) -> str:
    """Collapse internal whitespace and strip — TOC labels often span source lines."""
    return " ".join(text.split()) if text else ""


def _resolve(base: str, href: str) -> str:
    """Resolve a manifest/TOC href (relative to the OPF dir) to a zip entry name."""
    href = unquote(href.split("#", 1)[0])
    joined = posixpath.join(base, href) if base else href
    return posixpath.normpath(joined)


def _read_root(zf: zipfile.ZipFile, name: str) -> ET.Element | None:
    """Parse a zip member as XML, returning None if it is missing or malformed."""
    try:
        with zf.open(name) as fh:
            return ET.parse(fh).getroot()
    except (KeyError, ET.ParseError):
        return None


def _opf_path(zf: zipfile.ZipFile) -> str:
    """Resolve the package (OPF) document path from META-INF/container.xml."""
    root = _read_root(zf, _CONTAINER_PATH)
    if root is not None:
        for el in root.iter():
            if _localname(el.tag) == "rootfile" and el.get("full-path"):
                return el.get("full-path", "")
    raise ValueError("EPUB has no readable rootfile path (META-INF/container.xml)")


def _parse_opf(root: ET.Element) -> tuple[dict[str, tuple[str, str, str]], str | None]:
    """Extract the manifest and the spine's NCX reference from the OPF root.

    Returns ``(manifest, spine_toc_id)`` where manifest maps an item id to
    ``(href, media_type, properties)`` in document order.
    """
    manifest: dict[str, tuple[str, str, str]] = {}
    spine_toc: str | None = None
    for el in root.iter():
        ln = _localname(el.tag)
        if ln == "item":
            item_id = el.get("id")
            href = el.get("href")
            if item_id and href:
                manifest[item_id] = (href, (el.get("media-type") or "").lower(), el.get("properties") or "")
        elif ln == "spine":
            spine_toc = el.get("toc")
    return manifest, spine_toc


def _find_toc_hrefs(manifest: dict[str, tuple[str, str, str]], spine_toc: str | None) -> tuple[str | None, str | None]:
    """Locate the NCX (EPUB 2) and nav (EPUB 3) TOC hrefs within the manifest."""
    ncx_href: str | None = None
    nav_href: str | None = None
    # The spine's ``toc`` attribute is the authoritative NCX pointer; fall back
    # to a media-type scan for EPUB 2 files that omit it.
    if spine_toc and spine_toc in manifest:
        ncx_href = manifest[spine_toc][0]
    for href, media_type, properties in manifest.values():
        if ncx_href is None and media_type == _NCX_MEDIA_TYPE:
            ncx_href = href
        if "nav" in properties.split():
            nav_href = href
    return ncx_href, nav_href


def _titles_from_ncx(root: ET.Element, ncx_dir: str = "", nav_target: str | None = None) -> list[str]:
    """Extract navPoint labels from an NCX navMap in document order (depth-first).

    ``nav_target`` is the resolved zip path of the EPUB 3 nav document, if any. A
    navPoint pointing at it is the TOC's self-reference (e.g. a "Table of
    Contents" entry), which is not a chapter, so it is skipped. The EPUB 3 nav's
    own TOC list never self-lists, so this keeps the two sources in agreement.
    """
    nav_map = next((el for el in root.iter() if _localname(el.tag) == "navmap"), None)
    if nav_map is None:
        return []

    titles: list[str] = []

    def walk(node: ET.Element) -> None:
        for child in node:
            if _localname(child.tag) != "navpoint":
                continue
            label, src = _navpoint_label_src(child)
            if label and not (nav_target and src and _resolve(ncx_dir, src) == nav_target):
                titles.append(label)
            walk(child)

    walk(nav_map)
    return titles


def _navpoint_label_src(navpoint: ET.Element) -> tuple[str, str]:
    """Read a navPoint's own ``navLabel > text`` and ``content@src`` (direct children)."""
    label, src = "", ""
    for child in navpoint:
        ln = _localname(child.tag)
        if ln == "navlabel" and not label:
            for sub in child:
                if _localname(sub.tag) == "text":
                    label = _norm(sub.text)
                    break
        elif ln == "content" and not src:
            src = child.get("src", "")
    return label, src


class _NavTocParser(HTMLParser):
    """Pull the ordered entry labels out of an EPUB 3 nav 'toc' list.

    EPUB 3 nav documents are XHTML; rather than require strict XML, we use the
    tolerant stdlib HTML parser. Capture begins inside the ``<nav>`` whose
    attributes mark it as the TOC (matching ebooklib's ``//nav[@*='toc']``) and
    each ``<a>`` / heading ``<span>`` label is emitted on its closing tag.
    """

    def __init__(self, any_nav: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.titles: list[str] = []
        self._any_nav = any_nav
        self._nav_seen = False
        self._in_toc = False
        self._cap_tag: str | None = None
        self._cap_nest = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "nav":
            is_toc = any(v and ("toc" in v.split() or v == "doc-toc") for _, v in attrs)
            if is_toc or (self._any_nav and not self._nav_seen):
                self._in_toc = True
            self._nav_seen = True
            return
        if not self._in_toc:
            return
        if self._cap_tag is not None:
            if tag == self._cap_tag:
                self._cap_nest += 1
            return
        if tag in ("a", "span"):
            self._cap_tag = tag
            self._cap_nest = 0
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav":
            self._in_toc = False
            return
        if not self._in_toc or self._cap_tag is None or tag != self._cap_tag:
            return
        if self._cap_nest > 0:
            self._cap_nest -= 1
            return
        text = _norm("".join(self._buf))
        if text:
            self.titles.append(text)
        self._cap_tag = None
        self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_toc and self._cap_tag is not None:
            self._buf.append(data)


def _titles_from_nav(data: bytes) -> list[str]:
    """Extract TOC entry labels from EPUB 3 nav document bytes."""
    text = data.decode("utf-8", errors="replace")
    parser = _NavTocParser()
    parser.feed(text)
    if not parser.titles:
        # No nav was explicitly marked as the TOC; fall back to the first one.
        parser = _NavTocParser(any_nav=True)
        parser.feed(text)
    return parser.titles


class EpubParser(BaseTitleRefParser):
    short_name = "EPUB"

    def parse(self, file_path: str, ref_name: str) -> TitleReference:
        """Parse an EPUB file and extract chapter titles from its TOC.

        An EPUB is a ZIP of XML/XHTML, so this reads it with the standard library
        only. Title sources are tried in the same order as the EPUB spec layers
        them: the EPUB 2 NCX TOC, then the EPUB 3 nav document, then a fallback to
        spine document filenames.
        """
        try:
            with zipfile.ZipFile(file_path) as zf:
                titles = self._extract_titles(zf)
        except zipfile.BadZipFile as e:
            raise ValueError(f"Could not read EPUB: not a valid ZIP container ({e})") from e

        titles = [t for t in titles if t]
        if not titles:
            raise ValueError("Could not extract any chapter titles from EPUB")

        name = self.ellipsize_name(ref_name)
        logger.info(f"Parsed {ref_name} as EPUB Title Reference ({len(titles)} titles)")
        return TitleReference(
            type=TitleRefType.EPUB,
            name=f"EPUB File ({name})",
            short_name=self.short_name,
            description=f'Chapter titles extracted from EPUB file "{name}"',
            metadata={"File": ref_name},
            titles=titles,
        )

    def _extract_titles(self, zf: zipfile.ZipFile) -> list[str]:
        opf_path = _opf_path(zf)
        opf_root = _read_root(zf, opf_path)
        if opf_root is None:
            raise ValueError(f"Could not read EPUB package document ({opf_path})")

        manifest, spine_toc = _parse_opf(opf_root)
        base = posixpath.dirname(opf_path)
        ncx_href, nav_href = _find_toc_hrefs(manifest, spine_toc)
        nav_target = _resolve(base, nav_href) if nav_href else None

        # 1) EPUB 2 NCX TOC.
        if ncx_href:
            ncx_path = _resolve(base, ncx_href)
            ncx_root = _read_root(zf, ncx_path)
            if ncx_root is not None:
                titles = _titles_from_ncx(ncx_root, posixpath.dirname(ncx_path), nav_target)
                if titles:
                    return titles

        # 2) EPUB 3 nav document.
        if nav_href:
            try:
                with zf.open(_resolve(base, nav_href)) as fh:
                    nav_data = fh.read()
                titles = _titles_from_nav(nav_data)
                if titles:
                    return titles
            except KeyError:
                pass

        # 3) Fallback: derive titles from spine document filenames.
        titles = []
        for href, media_type, _ in manifest.values():
            if media_type not in _DOCUMENT_MEDIA_TYPES:
                continue
            stem = href.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            label = stem.replace("-", " ").replace("_", " ").strip()
            if label:
                titles.append(label)
        return titles
