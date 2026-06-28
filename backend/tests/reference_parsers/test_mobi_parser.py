"""Tests for the stdlib-only MOBI title parser (app/services/reference_parsers/mobi_parser.py).

MOBI files are built in-process as minimal Palm Databases so the suite needs no
binary fixtures. The builders below mirror exactly what the parser reads: the
NCX index (INDX header + TAGX tag table + per-entry IDXT + CNCX label strings)
for tier 1, and an inline ``<guide type="toc">`` text record for tier 3.
"""

import struct

import pytest

from app.services.reference_parsers.mobi_parser import MobiParser

_NO_REC = 0xFFFFFFFF

# The NCX tag table, matching what real kindlegen output emits (control byte
# count = 1): position, length, CNCX label offset, depth, parent, first/last
# child, then the terminating row.
_TAGX = [
    (1, 1, 0x01, 0),
    (2, 1, 0x02, 0),
    (3, 1, 0x04, 0),
    (4, 1, 0x08, 0),
    (21, 1, 0x10, 0),
    (22, 1, 0x20, 0),
    (23, 1, 0x40, 0),
    (0, 0, 0x00, 1),
]


def _varint(value: int) -> bytes:
    """Encode a Mobipocket forward varint (high bit set on the final byte)."""
    parts = [value & 0x7F]
    value >>= 7
    while value:
        parts.append(value & 0x7F)
        value >>= 7
    parts.reverse()
    parts[-1] |= 0x80
    return bytes(parts)


def _indx_header(*, start: int, count: int, code: int, total: int, ncncx: int) -> bytes:
    # b"INDX" + 13 big-endian uint32 fields (len, nul1, type, gen, start, count,
    # code, lng, total, ordt, ligt, nligt, ncncx).
    return b"INDX" + struct.pack(">13L", 0, 0, 0, 0, start, count, code, 0, total, 0, 0, 0, ncncx)


def _tagx_block() -> bytes:
    rows = b"".join(struct.pack(">4B", *row) for row in _TAGX)
    return b"TAGX" + struct.pack(">II", 8 + len(rows), 1) + rows


def _entry(ident: bytes, tags: dict[int, int]) -> bytes:
    """Build one index entry: ident, a control byte, then present tag values."""
    control = 0
    for tag, _n, mask, _end in _TAGX:
        if tag in tags:
            control |= mask
    body = bytes([control])
    for tag, _n, _mask, end in _TAGX:
        if end & 0x01:
            continue
        if tag in tags:
            body += _varint(tags[tag])
    return bytes([len(ident)]) + ident + body


def _cncx(labels: list[str]) -> tuple[bytes, list[int]]:
    """Pack labels into a CNCX record, returning (bytes, per-label start offsets)."""
    blob = bytearray()
    offsets = []
    for label in labels:
        offsets.append(len(blob))
        encoded = label.encode("utf-8")
        blob += _varint(len(encoded)) + encoded
    return bytes(blob), offsets


def _ncx_records(entries: list[dict[int, int]], labels: list[str]) -> list[bytes]:
    """Build the three NCX records: meta (INDX+TAGX), data (entries+IDXT), CNCX."""
    cncx, offsets = _cncx(labels)
    # Each entry references its label's CNCX offset via tag 3.
    entry_blobs = [_entry(b"%03d" % i, {3: offsets[i], **tags}) for i, tags in enumerate(entries)]

    header_len = len(_indx_header(start=0, count=0, code=0, total=0, ncncx=0))
    entry_offsets = []
    pos = header_len
    for blob in entry_blobs:
        entry_offsets.append(pos)
        pos += len(blob)
    idxt = b"IDXT" + b"".join(struct.pack(">H", off) for off in entry_offsets)
    data_rec = (
        _indx_header(start=pos, count=len(entry_blobs), code=65001, total=len(entry_blobs), ncncx=0)
        + b"".join(entry_blobs)
        + idxt
    )
    meta_rec = _indx_header(start=0, count=1, code=65001, total=len(entry_blobs), ncncx=1) + _tagx_block()
    return [meta_rec, data_rec, cncx]


def _record0(*, compression: int = 1, text_rec_count: int = 0, ncxidx: int = _NO_REC, encoding: int = 65001) -> bytes:
    palmdoc = struct.pack(">HHIHHHH", compression, 0, 0, text_rec_count, 4096, 0, 0)
    mobi = bytearray(232)
    mobi[0:4] = b"MOBI"
    struct.pack_into(">I", mobi, 4, 232)  # MOBI header length
    struct.pack_into(">I", mobi, 8, 2)  # MOBI type = book
    struct.pack_into(">I", mobi, 12, encoding)  # text encoding (record-0 offset 28)
    struct.pack_into(">I", mobi, 20, 6)  # file version (record-0 offset 36)
    struct.pack_into(">I", mobi, 228, ncxidx)  # NCX index record (record-0 offset 244)
    return palmdoc + bytes(mobi)


def _palm_db(records: list[bytes]) -> bytes:
    num = len(records)
    header = struct.pack(">32sHHIIIIII4s4sIIH", b"TestBook", 0, 0, 0, 0, 0, 0, 0, 0, b"BOOK", b"MOBI", 0, 0, num)
    data_start = 78 + 8 * num
    offsets = []
    pos = data_start
    for rec in records:
        offsets.append(pos)
        pos += len(rec)
    reclist = b"".join(struct.pack(">I", off) + b"\x00\x00\x00\x00" for off in offsets)
    return header + reclist + b"".join(records)


def _write_ncx_mobi(path, entries: list[dict[int, int]], labels: list[str]) -> None:
    # Records: 0=headers, 1=meta INDX, 2=data INDX, 3=CNCX. ncxidx points at record 1.
    records = [_record0(ncxidx=1)] + _ncx_records(entries, labels)
    path.write_bytes(_palm_db(records))


def _write_inline_toc_mobi(path, anchors: list[str]) -> None:
    toc_page = b"".join(b"<p><a filepos=%010d>%s</a></p>" % (i + 1, a.encode("utf-8")) for i, a in enumerate(anchors))
    head_tmpl = b'<html><head><guide><reference type="toc" filepos=%010d /></guide></head>'
    head = head_tmpl % len(head_tmpl % 0)  # filepos -> start of the body (the page break before the TOC)
    body = b"<mbp:pagebreak/>" + toc_page + b"<mbp:pagebreak/>body text here"
    text = head + body
    records = [_record0(compression=1, text_rec_count=1, ncxidx=_NO_REC), text]
    path.write_bytes(_palm_db(records))


def test_ncx_flat_toc(tmp_path):
    path = tmp_path / "flat.mobi"
    entries = [{1: 100}, {1: 200}, {1: 300}]
    _write_ncx_mobi(path, entries, ["Prologue", "Chapter One", "Chapter Two"])
    ref = MobiParser().parse(str(path), "flat.mobi")
    assert ref.titles == ["Prologue", "Chapter One", "Chapter Two"]
    assert ref.short_name == "MOBI"
    assert ref.type.value == "mobi"


def test_ncx_hierarchical_reading_order(tmp_path):
    # Entries are stored grouped by depth (parents 0..2, then children 3..4); the
    # parser must nest the children after their parent via tags 22/23.
    path = tmp_path / "tree.mobi"
    entries = [
        {1: 100, 4: 0, 22: 3, 23: 4},  # 0 Part One -> children 3,4
        {1: 500, 4: 0},  # 1 Part Two
        {1: 900, 4: 0},  # 2 Afterword
        {1: 150, 4: 1},  # 3 Chapter A (child of Part One)
        {1: 300, 4: 1},  # 4 Chapter B (child of Part One)
    ]
    labels = ["Part One", "Part Two", "Afterword", "Chapter A", "Chapter B"]
    _write_ncx_mobi(path, entries, labels)
    ref = MobiParser().parse(str(path), "tree.mobi")
    assert ref.titles == ["Part One", "Chapter A", "Chapter B", "Part Two", "Afterword"]


def test_ncx_decodes_html_entities_and_whitespace(tmp_path):
    path = tmp_path / "ent.mobi"
    _write_ncx_mobi(path, [{1: 1}, {1: 2}], ["Pen &amp; Paper", "And . . .  So\nIt Begins"])
    ref = MobiParser().parse(str(path), "ent.mobi")
    assert ref.titles == ["Pen & Paper", "And . . . So It Begins"]


def test_inline_guide_toc(tmp_path):
    path = tmp_path / "guide.mobi"
    _write_inline_toc_mobi(path, ["Chapter One", "Chapter Two", "Chapter Three"])
    ref = MobiParser().parse(str(path), "guide.mobi")
    assert ref.titles == ["Chapter One", "Chapter Two", "Chapter Three"]


def test_inline_toc_single_anchor_rejected(tmp_path):
    # A lone anchor (e.g. a "Start" link) is not a table of contents.
    path = tmp_path / "lone.mobi"
    _write_inline_toc_mobi(path, ["Start"])
    with pytest.raises(ValueError, match="Could not extract any chapter titles"):
        MobiParser().parse(str(path), "lone.mobi")


def test_no_toc_raises(tmp_path):
    # No NCX index and no inline guide -> nothing to extract.
    path = tmp_path / "empty.mobi"
    path.write_bytes(_palm_db([_record0(ncxidx=_NO_REC, text_rec_count=1, compression=1), b"<html>plain</html>"]))
    with pytest.raises(ValueError, match="Could not extract any chapter titles"):
        MobiParser().parse(str(path), "empty.mobi")


def test_short_mobi_header_does_not_misread_exth_as_ncx(tmp_path):
    # An older 200-byte MOBI header puts the EXTH block where offset 244 (the NCX
    # pointer) would be. Here those EXTH bytes spell record 1 — a decoy NCX whose
    # label is "WRONG". The parser must NOT read the pointer for a short header.
    palmdoc = struct.pack(">HHIHHHH", 1, 0, 0, 0, 4096, 0, 0)
    hlen = 200
    mobi = bytearray(hlen)
    mobi[0:4] = b"MOBI"
    struct.pack_into(">I", mobi, 4, hlen)  # MOBI header length (too short to hold the NCX pointer)
    struct.pack_into(">I", mobi, 112, 0x40)  # EXTH-present flag (record-0 offset 128)
    # EXTH starts at record-0 offset 16+200=216; craft it so offset 244 reads as record 1.
    exth = b"EXTH" + struct.pack(">II", 32, 1) + struct.pack(">II", 100, 20) + (b"\x00" * 8 + b"\x00\x00\x00\x01")
    rec0 = palmdoc + bytes(mobi) + exth
    assert len(rec0) == 248  # long enough that a naive read of offset 244 would fire
    records = [rec0] + _ncx_records([{1: 1}], ["WRONG"])
    path = tmp_path / "short.mobi"
    path.write_bytes(_palm_db(records))
    with pytest.raises(ValueError, match="Could not extract any chapter titles"):
        MobiParser().parse(str(path), "short.mobi")


def test_invalid_file_raises(tmp_path):
    path = tmp_path / "bad.mobi"
    path.write_bytes(b"not a mobi file")
    with pytest.raises(ValueError, match="Could not read MOBI"):
        MobiParser().parse(str(path), "bad.mobi")
