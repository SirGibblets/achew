"""Tests for the chunked Reference upload endpoint (app/api/routes/references.py).

Uploads arrive as a sequence of ordered chunks so that ebook References stay
under the ~1MB request-body cap that reverse proxies commonly apply. These tests
cover the assembly of those chunks; the parsers themselves are covered by the
reference_parsers suite.
"""

import io
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import references

CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>
</container>
"""

OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>
  <spine toc="ncx"/>
</package>
"""

NCX = """<?xml version="1.0"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="n1"><navLabel><text>Chapter One</text></navLabel><content src="c1.xhtml"/></navPoint>
    <navPoint id="n2"><navLabel><text>Chapter Two</text></navLabel><content src="c2.xhtml"/></navPoint>
  </navMap>
</ncx>
"""


def _epub_bytes() -> bytes:
    """A minimal but valid EPUB, small enough to split into byte-sized chunks."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", OPF)
        zf.writestr("OEBPS/toc.ncx", NCX)
    return buf.getvalue()


class StubPipeline:
    def __init__(self):
        self.chapter_refs = []
        self.title_refs = []
        self.book = None


class StubAppState:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.broadcasts = 0

    async def broadcast_references_update(self):
        self.broadcasts += 1


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """Wire the router to a stub pipeline and an isolated upload directory."""
    state = StubAppState(StubPipeline())
    monkeypatch.setattr(references, "get_app_state", lambda: state)
    monkeypatch.setattr(references, "_UPLOAD_DIR", str(tmp_path / "uploads"))
    references._expected_chunk.clear()
    return state.pipeline


@pytest.fixture
def client(pipeline):
    app = FastAPI()
    app.include_router(references.router, prefix="/api")
    return TestClient(app)


def _post(client, data: bytes, *, name="book.epub", index=0, total=1, upload_id="abc123"):
    return client.post(
        "/api/pipeline/references/upload",
        files={"file": (name, data, "application/epub+zip")},
        data={"upload_id": upload_id, "index": str(index), "total": str(total)},
    )


def _chunks(data: bytes, count: int) -> list[bytes]:
    size = -(-len(data) // count)  # ceil, so the last chunk is the short one
    return [data[i * size : (i + 1) * size] for i in range(count)]


def test_chunks_are_assembled_and_parsed(client, pipeline):
    parts = _chunks(_epub_bytes(), 3)

    for i, part in enumerate(parts):
        response = _post(client, part, index=i, total=3)
        assert response.status_code == 200
        if i < 2:
            # Interim chunks acknowledge progress rather than parsing.
            assert response.json() == {"upload_id": "abc123", "received": i + 1, "total": 3}

    assert response.json()["titles"] == ["Chapter One", "Chapter Two"]
    assert len(pipeline.title_refs) == 1


def test_upload_without_chunk_fields_still_works(client, pipeline):
    """A plain one-request upload is the degenerate single-chunk case."""
    response = client.post(
        "/api/pipeline/references/upload",
        files={"file": ("book.epub", _epub_bytes(), "application/epub+zip")},
    )

    assert response.status_code == 200
    assert response.json()["titles"] == ["Chapter One", "Chapter Two"]


def test_part_file_is_cleaned_up_after_parsing(client, tmp_path):
    parts = _chunks(_epub_bytes(), 2)
    for i, part in enumerate(parts):
        _post(client, part, index=i, total=2)

    assert list((tmp_path / "uploads").iterdir()) == []
    assert references._expected_chunk == {}


def test_out_of_order_chunk_is_rejected(client, tmp_path):
    parts = _chunks(_epub_bytes(), 3)
    assert _post(client, parts[0], index=0, total=3).status_code == 200

    # Chunk 1 never arrives — concatenating chunk 2 here would silently corrupt.
    response = _post(client, parts[2], index=2, total=3)

    assert response.status_code == 409
    assert list((tmp_path / "uploads").iterdir()) == []


@pytest.mark.parametrize("index,total", [(0, 0), (-1, 3), (3, 3)])
def test_nonsense_chunk_bounds_are_rejected(client, index, total):
    assert _post(client, b"data", index=index, total=total).status_code == 400


def test_unsupported_type_is_rejected_on_the_first_chunk(client):
    """Fail fast, rather than after the client has uploaded the whole file."""
    response = _post(client, b"%PDF-1.4", name="book.pdf", index=0, total=100)

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


@pytest.mark.parametrize("upload_id", ["../escape", "a/b", "with space", "x" * 65])
def test_upload_id_must_be_a_safe_token(client, upload_id):
    """The id lands in a filename, so it must not be able to escape the directory."""
    assert _post(client, b"data", upload_id=upload_id).status_code == 400


def test_oversized_upload_is_rejected_without_a_413(client, monkeypatch):
    """413 is reserved for proxies — the frontend reads it as 'not Achew'."""
    monkeypatch.setattr(references, "_MAX_UPLOAD_BYTES", 16)

    response = _post(client, b"x" * 32, index=0, total=2)

    assert response.status_code == 400
    assert "too large" in response.json()["detail"]
