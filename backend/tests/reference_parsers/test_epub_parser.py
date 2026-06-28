"""Tests for the stdlib-only EPUB title parser (app/services/reference_parsers/epub_parser.py).

EPUBs are built in-process as minimal ZIP containers so the suite needs no binary
fixtures. Each test targets one of the parser's three title sources: the EPUB 2
NCX TOC, the EPUB 3 nav document, and the spine-filename fallback.
"""

import zipfile

import pytest

from app.services.reference_parsers.epub_parser import EpubParser

CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _write_epub(path, *, opf: str, extra: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # The mimetype entry must be first and stored, per the EPUB spec.
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        for name, content in extra.items():
            zf.writestr(f"OEBPS/{name}", content)


def _epub2(tmp_path):
    opf = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
      <manifest>
        <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
        <item id="c1" href="text/chap1.xhtml" media-type="application/xhtml+xml"/>
        <item id="c2" href="text/chap2.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
      <spine toc="ncx">
        <itemref idref="c1"/>
        <itemref idref="c2"/>
      </spine>
    </package>
    """
    ncx = """<?xml version="1.0"?>
    <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
      <navMap>
        <navPoint id="n1" playOrder="1">
          <navLabel><text>  Prologue  </text></navLabel>
          <content src="text/chap1.xhtml"/>
          <navPoint id="n1a" playOrder="2">
            <navLabel><text>Prologue, Part Two</text></navLabel>
            <content src="text/chap1.xhtml#p2"/>
          </navPoint>
        </navPoint>
        <navPoint id="n2" playOrder="3">
          <navLabel><text>Chapter One</text></navLabel>
          <content src="text/chap2.xhtml"/>
        </navPoint>
      </navMap>
    </ncx>
    """
    path = tmp_path / "book2.epub"
    _write_epub(path, opf=opf, extra={"toc.ncx": ncx, "text/chap1.xhtml": "<html/>", "text/chap2.xhtml": "<html/>"})
    return path


def _epub3(tmp_path, *, nav: str):
    opf = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
      <manifest>
        <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
        <item id="c1" href="text/chap1.xhtml" media-type="application/xhtml+xml"/>
        <item id="c2" href="text/chap2.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
      <spine>
        <itemref idref="c1"/>
        <itemref idref="c2"/>
      </spine>
    </package>
    """
    path = tmp_path / "book3.epub"
    _write_epub(path, opf=opf, extra={"nav.xhtml": nav, "text/chap1.xhtml": "<html/>", "text/chap2.xhtml": "<html/>"})
    return path


def test_epub2_ncx_toc(tmp_path):
    ref = EpubParser().parse(str(_epub2(tmp_path)), "book2.epub")
    # Depth-first document order, whitespace normalized, nested navPoint included.
    assert ref.titles == ["Prologue", "Prologue, Part Two", "Chapter One"]
    assert ref.short_name == "EPUB"


def test_epub3_nav_toc(tmp_path):
    nav = """<?xml version="1.0" encoding="utf-8"?>
    <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
      <body>
        <nav epub:type="landmarks"><ol><li><a href="text/chap1.xhtml">Start</a></li></ol></nav>
        <nav epub:type="toc">
          <ol>
            <li><a href="text/chap1.xhtml"><span>1.</span> Chapter One</a>
              <ol><li><a href="text/chap1.xhtml#s2">Section Two</a></li></ol>
            </li>
            <li><a href="text/chap2.xhtml">Chapter &amp; Two</a></li>
          </ol>
        </nav>
      </body>
    </html>
    """
    ref = EpubParser().parse(str(_epub3(tmp_path, nav=nav)), "book3.epub")
    # The landmarks nav is ignored; nested text and entities are handled.
    assert ref.titles == ["1. Chapter One", "Section Two", "Chapter & Two"]


def test_ncx_skips_self_referential_toc_entry(tmp_path):
    # A book carrying both an NCX (preferred) and a nav doc. The NCX lists a
    # "Table of Contents" navPoint pointing at the nav document itself — a
    # self-reference that is not a chapter and must be dropped.
    opf = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
      <manifest>
        <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
        <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
        <item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
      <spine toc="ncx"><itemref idref="c1"/></spine>
    </package>
    """
    ncx = """<?xml version="1.0"?>
    <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
      <navMap>
        <navPoint id="cov"><navLabel><text>Cover</text></navLabel><content src="cover.xhtml"/></navPoint>
        <navPoint id="toc"><navLabel><text>Table of Contents</text></navLabel><content src="nav.xhtml"/></navPoint>
        <navPoint id="c1"><navLabel><text>Chapter One</text></navLabel><content src="chap1.xhtml"/></navPoint>
      </navMap>
    </ncx>
    """
    path = tmp_path / "selfref.epub"
    _write_epub(path, opf=opf, extra={"toc.ncx": ncx, "nav.xhtml": "<html/>", "chap1.xhtml": "<html/>"})
    ref = EpubParser().parse(str(path), "selfref.epub")
    assert ref.titles == ["Cover", "Chapter One"]


def test_epub3_filename_fallback_when_nav_empty(tmp_path):
    # A nav doc with no toc-marked nav and no anchors → fall through to filenames.
    nav = """<html xmlns="http://www.w3.org/1999/xhtml"><body><p>no toc here</p></body></html>"""
    ref = EpubParser().parse(str(_epub3(tmp_path, nav=nav)), "book3.epub")
    # nav.xhtml is itself a document item, then the two chapters.
    assert ref.titles == ["nav", "chap1", "chap2"]


def test_ncx_normalizes_whitespace(tmp_path):
    # Real books embed non-breaking spaces and double spaces in TOC labels.
    # We collapse runs of any whitespace to single spaces so titles display cleanly.
    ncx = """<?xml version="1.0"?>
    <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
      <navMap>
        <navPoint id="n1"><navLabel><text>And . . . So It Begins</text></navLabel><content src="a.xhtml"/></navPoint>
        <navPoint id="n2"><navLabel><text>Also by This Author</text></navLabel><content src="b.xhtml"/></navPoint>
        <navPoint id="n3"><navLabel><text>CHAPTER ONE  How It Began</text></navLabel><content src="c.xhtml"/></navPoint>
      </navMap>
    </ncx>
    """
    opf = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="2.0">
      <manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>
      <spine toc="ncx"/>
    </package>
    """
    path = tmp_path / "ws.epub"
    _write_epub(path, opf=opf, extra={"toc.ncx": ncx})
    ref = EpubParser().parse(str(path), "ws.epub")
    assert ref.titles == ["And . . . So It Begins", "Also by This Author", "CHAPTER ONE How It Began"]


def test_invalid_epub_raises(tmp_path):
    path = tmp_path / "bad.epub"
    path.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="Could not read EPUB"):
        EpubParser().parse(str(path), "bad.epub")


def test_no_titles_raises(tmp_path):
    # Valid container, but a manifest with no documents and no TOC.
    opf = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
      <manifest><item id="css" href="style.css" media-type="text/css"/></manifest>
      <spine/>
    </package>
    """
    path = tmp_path / "empty.epub"
    _write_epub(path, opf=opf, extra={"style.css": "body{}"})
    with pytest.raises(ValueError, match="Could not extract any chapter titles"):
        EpubParser().parse(str(path), "empty.epub")
