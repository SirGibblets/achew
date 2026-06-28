import html
import logging
import re
import struct

from ...models.references import TitleReference, TitleRefType
from .base_parser import BaseTitleRefParser

logger = logging.getLogger(__name__)

# Sentinel a MOBI header uses for "no such record".
_NO_REC = 0xFFFFFFFF

# PalmDOC header compression field (record 0, offset 0).
_PALMDOC = 2
_HUFFCDIC = 17480


# ---- Palm Database container --------------------------------------------------
def _read_records(data: bytes) -> list[bytes]:
    """Split a Palm Database file into its record byte-slices.

    A MOBI is a PDB: a 78-byte header, a list of 8-byte record-info entries (each
    holding the record's absolute file offset), then the record payloads.
    """
    (num,) = struct.unpack_from(">H", data, 76)
    offsets = [struct.unpack_from(">I", data, 78 + 8 * i)[0] for i in range(num)]
    offsets.append(len(data))
    return [data[offsets[i] : offsets[i + 1]] for i in range(num)]


# ---- record-0 headers ---------------------------------------------------------
def _exth(rec0: bytes, mobi_header_len: int) -> dict[int, bytes]:
    """Parse the EXTH key->value metadata map from record 0, if present."""
    (flags,) = struct.unpack_from(">I", rec0, 128)
    if not (flags & 0x40):
        return {}
    base = 16 + mobi_header_len
    if rec0[base : base + 4] != b"EXTH":
        return {}
    (count,) = struct.unpack_from(">I", rec0, base + 8)
    out: dict[int, bytes] = {}
    pos = base + 12
    for _ in range(count):
        rtype, rlen = struct.unpack_from(">II", rec0, pos)
        out[rtype] = rec0[pos + 8 : pos + rlen]
        pos += rlen
    return out


def _mobi_header(rec0: bytes) -> dict | None:
    """Read the fields we need from a record-0 MOBI header, or None if absent."""
    if rec0[16:20] != b"MOBI":
        return None
    (hlen,) = struct.unpack_from(">I", rec0, 20)
    ncxidx = _NO_REC
    # The NCX-index pointer sits at offset 244, present only in MOBI headers long
    # enough to reach it (>= 232 bytes). Shorter (older) headers put the EXTH block
    # there, so reading unconditionally would misinterpret "EXTH" as a record number.
    if hlen >= 232 and len(rec0) >= 248:
        (ncxidx,) = struct.unpack_from(">I", rec0, 244)
    return {"ncxidx": ncxidx, "exth": _exth(rec0, hlen)}


def _resolve_ncx_record(recs: list[bytes]) -> int:
    """Find the absolute record number of the NCX index, or ``_NO_REC``.

    A combo (MOBI 6 + KF8) file carries the richer TOC in its KF8 part, whose
    headers live at the boundary record named by EXTH 121; record numbers there
    are relative to that boundary. Plain files use record 0's pointer directly.
    """
    h0 = _mobi_header(recs[0])
    if h0 is None:
        return _NO_REC
    boundary = h0["exth"].get(121)
    if boundary and len(boundary) == 4:
        (brec,) = struct.unpack(">I", boundary)
        if brec != _NO_REC and brec < len(recs):
            hk = _mobi_header(recs[brec])
            if hk is not None and hk["ncxidx"] != _NO_REC:
                return brec + hk["ncxidx"]
    if h0["ncxidx"] != _NO_REC:
        return h0["ncxidx"]
    return _NO_REC


# ---- Mobipocket variable-width integers --------------------------------------
def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a forward varint: 7 bits/byte, the byte with the high bit set ends it."""
    value = 0
    consumed = 0
    while pos + consumed < len(data):
        byte = data[pos + consumed]
        consumed += 1
        value = (value << 7) | (byte & 0x7F)
        if byte & 0x80:
            break
    return value, consumed


# ---- INDX / TAGX / IDXT / CNCX (the NCX index) -------------------------------
_INDX_FIELDS = (
    "len",
    "nul1",
    "type",
    "gen",
    "start",
    "count",
    "code",
    "lng",
    "total",
    "ordt",
    "ligt",
    "nligt",
    "ncncx",
)


def _parse_indx_header(rec: bytes) -> dict:
    """Read an INDX record's fixed header (a run of big-endian uint32s from offset 4)."""
    vals = struct.unpack_from(">%dL" % len(_INDX_FIELDS), rec, 4)
    return dict(zip(_INDX_FIELDS, vals))


def _parse_tagx(rec: bytes) -> tuple[int, list[tuple[int, int, int, int]]]:
    """Locate the TAGX block in the index header; return (control_byte_count, tag_table).

    The tag table describes how each index entry encodes its tag values: a list of
    ``(tag, values_per_entry, bitmask, end_flag)`` rows.
    """
    i = rec.find(b"TAGX")
    if i < 0:
        return 0, []
    (tagx_len,) = struct.unpack_from(">I", rec, i + 4)
    (cbc,) = struct.unpack_from(">I", rec, i + 8)
    tags: list[tuple[int, int, int, int]] = []
    for off in range(i + 12, i + tagx_len, 4):
        tags.append((rec[off], rec[off + 1], rec[off + 2], rec[off + 3]))
    return cbc, tags


def _read_cncx(records: list[bytes]) -> dict[int, bytes]:
    """Map each CNCX string's start offset (in the concatenated CNCX) -> its bytes.

    The CNCX (compiled NCX) records hold the TOC label strings as a packed series
    of ``[varint length][bytes]`` pairs. Entry labels reference them by this offset.
    """
    blob = b"".join(records)
    out: dict[int, bytes] = {}
    pos = 0
    while pos < len(blob):
        length, consumed = _read_varint(blob, pos)
        if consumed == 0:  # guard against a zero-length read stalling
            break
        out[pos] = blob[pos + consumed : pos + consumed + length]
        pos += consumed + length
    return out


def _decode_entry_tags(entry: bytes, cbc: int, tagx: list[tuple[int, int, int, int]]) -> dict[int, list[int]]:
    """Decode one index entry's tag region into ``{tag: [values]}`` using the TAGX table."""
    ident_len = entry[0]
    start = 1 + ident_len
    # Pass 1: read the control bytes to learn how many values each present tag has.
    plan: list[tuple[int, int | None, int | None, int]] = []  # (tag, value_count, byte_count, num_values)
    control_index = 0
    data_ptr = start + cbc
    for tag, num_values, mask, end_flag in tagx:
        if end_flag & 0x01:
            control_index += 1
            continue
        value = entry[start + control_index] & mask
        if value == 0:
            continue
        if value == mask:
            if mask.bit_count() > 1:
                # A multi-bit mask saturated means the value count is a varint in the data.
                count, consumed = _read_varint(entry, data_ptr)
                data_ptr += consumed
                plan.append((tag, None, count, num_values))
            else:
                plan.append((tag, 1, None, num_values))
        else:
            shifted = mask
            while shifted & 0x01 == 0:
                shifted >>= 1
                value >>= 1
            plan.append((tag, value, None, num_values))
    # Pass 2: read the actual varint values from the data region.
    result: dict[int, list[int]] = {}
    for tag, value_count, byte_count, num_values in plan:
        vals: list[int] = []
        if value_count is not None:
            for _ in range(value_count * num_values):
                v, consumed = _read_varint(entry, data_ptr)
                data_ptr += consumed
                vals.append(v)
        elif byte_count is not None:
            consumed_total = 0
            while consumed_total < byte_count:
                v, consumed = _read_varint(entry, data_ptr)
                data_ptr += consumed
                consumed_total += consumed
                vals.append(v)
        result[tag] = vals
    return result


def _read_index_entries(data_rec: bytes, cbc: int, tagx: list[tuple[int, int, int, int]]) -> list[dict[int, list[int]]]:
    """Decode every entry in an index DATA record, located via its trailing IDXT block."""
    hdr = _parse_indx_header(data_rec)
    idxt_pos = hdr["start"]
    count = hdr["count"]
    offsets = [struct.unpack_from(">H", data_rec, idxt_pos + 4 + 2 * j)[0] for j in range(count)]
    offsets.append(idxt_pos)  # sentinel: the entries end where the IDXT block begins
    entries = []
    for j in range(count):
        entry = data_rec[offsets[j] : offsets[j + 1]]
        if entry:
            entries.append(_decode_entry_tags(entry, cbc, tagx))
    return entries


# NCX entry tags: 3 = label offset into the CNCX; 22/23 = first/last child entry
# index (the TOC hierarchy). Tag 1 (filepos) and 4 (depth) exist but aren't needed.
_LABEL_TAG = 3
_FIRSTCHILD_TAG = 22
_LASTCHILD_TAG = 23


def _child_range(tags: dict[int, list[int]], n: int) -> tuple[int, int] | None:
    """Return the (first, last) child entry-index range for an entry, if valid."""
    if tags.get(_FIRSTCHILD_TAG) and tags.get(_LASTCHILD_TAG):
        fc, lc = tags[_FIRSTCHILD_TAG][0], tags[_LASTCHILD_TAG][0]
        if 0 <= fc <= lc < n:
            return fc, lc
    return None


def _reading_order(entries: list[dict[int, list[int]]]) -> list[int]:
    """Depth-first traversal of the NCX tree, in storage order.

    Index entries are stored grouped by hierarchy level (all parents, then all
    children), but reading order nests each parent's children right after it.
    A parent names its children by index via tags 22/23, so we recurse those
    ranges from the roots (entries that are no one's child). Flat TOCs (no child
    tags) fall through to plain storage order.
    """
    n = len(entries)
    is_child = [False] * n
    for tags in entries:
        rng = _child_range(tags, n)
        if rng:
            for c in range(rng[0], rng[1] + 1):
                is_child[c] = True

    order: list[int] = []
    visited = [False] * n

    def walk(idx: int) -> None:
        if visited[idx]:
            return
        visited[idx] = True
        order.append(idx)
        rng = _child_range(entries[idx], n)
        if rng:
            for c in range(rng[0], rng[1] + 1):
                walk(c)

    for idx in range(n):
        if not is_child[idx]:
            walk(idx)
    # Safety net: emit any entry not reachable from a root (malformed hierarchy).
    for idx in range(n):
        if not visited[idx]:
            order.append(idx)
    return order


def _ncx_titles(recs: list[bytes]) -> list[str]:
    """Tier 1: read TOC labels from the NCX index, without decompressing the text."""
    ncxidx = _resolve_ncx_record(recs)
    if ncxidx == _NO_REC or ncxidx >= len(recs) or recs[ncxidx][:4] != b"INDX":
        return []
    hdr = _parse_indx_header(recs[ncxidx])
    cbc, tagx = _parse_tagx(recs[ncxidx])
    if not tagx:
        return []
    encoding = "utf-8" if hdr.get("code") == 65001 else "cp1252"
    n_data = hdr["count"]
    cncx = _read_cncx(recs[ncxidx + 1 + n_data : ncxidx + 1 + n_data + hdr["ncncx"]])

    entries: list[dict[int, list[int]]] = []
    for i in range(n_data):
        data_rec = recs[ncxidx + 1 + i]
        if data_rec[:4] == b"INDX":
            entries.extend(_read_index_entries(data_rec, cbc, tagx))

    titles: list[str] = []
    for idx in _reading_order(entries):
        offsets = entries[idx].get(_LABEL_TAG)
        if not offsets:
            continue
        raw = cncx.get(offsets[0])
        if raw is None:
            continue
        label = " ".join(html.unescape(raw.decode(encoding, errors="replace")).split())
        if label:
            titles.append(label)
    return titles


# ---- Tier 3: the inline-HTML <guide> TOC (books with no NCX index) -----------
_GUIDE_TOC_RE = re.compile(rb'<reference\b[^>]*\btype="toc"[^>]*>', re.IGNORECASE)
_FILEPOS_RE = re.compile(rb"filepos=0*(\d+)", re.IGNORECASE)
# Match a real <a ...>...</a> link; the negative lookbehind skips self-closing
# <a/> anchor-target tags, which otherwise swallow text up to the next </a>.
_ANCHOR_RE = re.compile(rb"<a\b[^>]*(?<!/)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_PAGEBREAK_RE = re.compile(rb"<mbp:pagebreak[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(rb"<[^>]+>")

# How far past the guide's filepos to look for the TOC page, and how many
# page-break-delimited pages within that window to consider.
_TOC_WINDOW_BYTES = 200_000
_TOC_MAX_PAGES = 12
# A real TOC has multiple entries; a lone anchor is a stray link, not a TOC.
_TOC_MIN_ENTRIES = 3


def _palmdoc_extend(out: bytearray, data: bytes) -> None:
    """Decompress one PalmDOC (LZ77-style) record, appending into shared ``out``.

    The buffer is shared across records because some encoders emit back-references
    that reach into the previous record's output; a reference pointing before the
    buffer start is filled with a space to keep byte offsets (filepos) aligned.
    """
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        i += 1
        if b == 0x00 or 0x09 <= b <= 0x7F:
            out.append(b)
        elif b <= 0x08:  # 1..8: a literal run of the next b bytes
            out += data[i : i + b]
            i += b
        elif b >= 0xC0:  # 0xC0..0xFF: a space followed by (b ^ 0x80)
            out += b" "
            out.append(b ^ 0x80)
        else:  # 0x80..0xBF: a (distance, length) back-reference (2 bytes)
            if i >= n:
                break
            lz = (b << 8) | data[i]
            i += 1
            distance = (lz >> 3) & 0x07FF
            length = (lz & 0x07) + 3
            if distance == 0:
                break
            for _ in range(length):
                out.append(out[-distance] if distance <= len(out) else 0x20)


def _book_text(recs: list[bytes]) -> bytes | None:
    """Decompress and concatenate the book's text records.

    Returns None for HUFF/CDIC-compressed books, which we don't decompress.
    """
    rec0 = recs[0]
    (compression,) = struct.unpack_from(">H", rec0, 0)
    (text_rec_count,) = struct.unpack_from(">H", rec0, 8)
    if compression == _HUFFCDIC:
        return None
    out = bytearray()
    for r in range(1, min(text_rec_count, len(recs) - 1) + 1):
        if compression == _PALMDOC:
            _palmdoc_extend(out, recs[r])
        else:
            out += recs[r]
    return bytes(out)


def _clean_label(raw: bytes, encoding: str) -> str:
    text = _TAG_RE.sub(b"", raw).decode(encoding, errors="replace")
    return " ".join(html.unescape(text).split())


def _inline_toc_titles(recs: list[bytes]) -> list[str]:
    """Tier 3: extract TOC labels from the inline ``<guide type="toc">`` page (MOBI 6).

    The guide reference's filepos lands at or just before the TOC page, but a
    stray anchor (a footnote marker, a "start" link) plus a page break often sit
    between it and the real list. So rather than trust the first anchor, scan the
    page-break-delimited pages in a window after the filepos and take the densest
    cluster of anchors — the actual table of contents. A lone anchor is rejected.
    """
    text = _book_text(recs)
    if text is None:
        return []
    ref = _GUIDE_TOC_RE.search(text)
    if not ref:
        return []
    fp = _FILEPOS_RE.search(ref.group(0))  # a placeholder 'filepos=XXXX' has no digits -> no match
    if not fp:
        return []
    start = int(fp.group(1))

    (code,) = struct.unpack_from(">I", recs[0], 28)
    encoding = "utf-8" if code == 65001 else "cp1252"

    window = text[start : start + _TOC_WINDOW_BYTES]
    best: list[str] = []
    for page in _PAGEBREAK_RE.split(window)[:_TOC_MAX_PAGES]:
        labels = [lbl for m in _ANCHOR_RE.finditer(page) if (lbl := _clean_label(m.group(1), encoding))]
        if len(labels) > len(best):
            best = labels
    return best if len(best) >= _TOC_MIN_ENTRIES else []


class MobiParser(BaseTitleRefParser):
    short_name = "MOBI"

    def parse(self, file_path: str, ref_name: str) -> TitleReference:
        """Parse a MOBI/AZW file and extract chapter titles from its table of contents.

        A MOBI is a Palm Database of records, read here with the standard library
        only. Title sources are tried in order: the NCX index (read straight from
        the compiled-NCX strings, no text decompression), then the inline-HTML
        ``<guide>`` TOC for older files that lack an NCX. Handles MOBI 6, KF8/AZW3,
        and combo files; DRM-encrypted and HUFF/CDIC-only books are not supported.
        """
        try:
            with open(file_path, "rb") as fh:
                data = fh.read()
            recs = _read_records(data)
            titles = _ncx_titles(recs) or _inline_toc_titles(recs)
        except (struct.error, IndexError) as e:
            raise ValueError(f"Could not read MOBI: not a valid MOBI/PDB container ({e})") from e

        titles = [t for t in titles if t]
        if not titles:
            raise ValueError("Could not extract any chapter titles from MOBI")

        name = self.ellipsize_name(ref_name)
        logger.info(f"Parsed {ref_name} as MOBI Title Reference ({len(titles)} titles)")
        return TitleReference(
            type=TitleRefType.MOBI,
            name=f"MOBI File ({name})",
            short_name=self.short_name,
            description=f'Chapter titles extracted from MOBI file "{name}"',
            metadata={"File": ref_name},
            titles=titles,
        )
