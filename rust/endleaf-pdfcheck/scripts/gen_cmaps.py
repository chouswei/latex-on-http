"""Generate src/cmapdata/{cmaps,unicode}.bin from the pinned pdfminer.six CMap data (ENDLEAF-R82).

Source: pdfminer/cmap/*.json.gz of pdfminer.six 20260107 (MIT), converted by pdfminer from
the Adobe cmap-resources (BSD-3-Clause, see src/cmapdata/NOTICE). Run with the reference
interpreter that has the pinned wheel, from the crate directory:

    python -I scripts/gen_cmaps.py

The decoded data is exactly pdfminer's: each CMap is its CODE2CID trie as shipped (pdfminer
builds the files from the Adobe cid2code tables, so there is no usecmap left to resolve; no
trie has an empty node, so a trie is fully given by its leaves), each Unicode map its
CID2UNICHR_H / CID2UNICHR_V.

Container (little endian): b"ELCM", u16 entry count, per entry u8 name length, name, u32
offset, u32 length (offsets from the end of the index); each entry is a raw-deflate blob.

CMap blob: u8 vertical, u8 kind.
  kind 0 (root): runs.
  kind 1 (derived): u8 base-name length, base name, u8 base scheme, u8 own scheme, runs
    to set, then removal runs. The start map is every base leaf whose code decodes to a
    code point under the base scheme, re-encoded under the own scheme (dropped when it
    cannot be encoded); then the removals, then the sets. Bases are always roots.
  runs: u32 count, per run u8 code length, code, LEB128 count, LEB128 first CID (codes
    rise by one as big-endian integers, CIDs by one). Removal runs have no CID.
Schemes: 0 bytes (the code itself), 1 UCS-2, 2 UTF-16BE, 3 UTF-32BE, 4 UTF-8 (strict).

Unicode blob: u32 count, per entry LEB128 CID delta, u8 UTF-8 length, UTF-8. The V blob
holds the V entries that differ from H, then u32 count and LEB128 CID deltas of the H
entries absent from V.
"""

import gzip
import json
import os
import struct
import sys
import zlib

import pdfminer

SRC = os.path.join(os.path.dirname(pdfminer.__file__), "cmap")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "cmapdata")
BYTES, UCS2, UTF16, UTF32, UTF8 = range(5)


def scheme_of(name: str) -> int:
    for tag, s in (("UCS2", UCS2), ("UTF16", UTF16), ("UTF32", UTF32), ("UTF8", UTF8)):
        if tag in name:
            return s
    return BYTES


def decode(s: int, code: bytes):
    if s == BYTES:
        return code
    if s == UCS2:
        return int.from_bytes(code, "big") if len(code) == 2 else None
    if s == UTF32:
        v = int.from_bytes(code, "big") if len(code) == 4 else None
        return v if v is not None and v <= 0x10FFFF else None
    try:
        t = code.decode("utf-16-be" if s == UTF16 else "utf-8")
    except UnicodeDecodeError:
        return None
    return ord(t) if len(t) == 1 else None


def encode(s: int, cp):
    if s == BYTES:
        return cp
    if s == UCS2:
        return cp.to_bytes(2, "big") if cp <= 0xFFFF else None
    if s == UTF32:
        return cp.to_bytes(4, "big")
    if 0xD800 <= cp <= 0xDFFF:
        return None
    return chr(cp).encode("utf-16-be" if s == UTF16 else "utf-8")


def flatten(d: dict, pre: bytes, out: dict) -> None:
    assert d, "empty trie node"
    for k, v in d.items():
        code = pre + bytes([int(k)])
        if isinstance(v, dict):
            flatten(v, code, out)
        else:
            out[code] = int(v)


def start_map(base: dict, bs: int, os_: int) -> dict:
    out = {}
    for code, cid in base.items():
        cp = decode(bs, code)
        if cp is None:
            continue
        c = encode(os_, cp)
        if c is not None:
            out[c] = cid
    return out


def leb(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def runs(items: list, with_cid: bool) -> bytes:
    """items: sorted (code, cid) pairs."""
    rs = []
    for code, cid in items:
        if rs:
            c0, n, f = rs[-1]
            if len(c0) == len(code) and int.from_bytes(c0, "big") + n == int.from_bytes(
                code, "big"
            ) and (not with_cid or f + n == cid):
                rs[-1][1] += 1
                continue
        rs.append([code, 1, cid])
    b = bytearray(struct.pack("<I", len(rs)))
    for code, n, f in rs:
        b += bytes([len(code)]) + code + leb(n) + (leb(f) if with_cid else b"")
    return bytes(b)


def leaves(name: str) -> tuple:
    with gzip.open(os.path.join(SRC, name + ".json.gz"), "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    flat: dict = {}
    flatten(data["CODE2CID"], b"", flat)
    return bool(data.get("IS_VERTICAL")), flat


def order(name: str) -> tuple:
    # Roots first: UTF-32 (widest code space), then UTF-16, UTF-8, UCS-2; H before V.
    rank = {UTF32: 0, UTF16: 1, UTF8: 2, UCS2: 3, BYTES: 4}[scheme_of(name)]
    return (rank, name.endswith("-V"), name)


def cmap_entries() -> list:
    names = sorted(
        (f[: -len(".json.gz")] for f in os.listdir(SRC) if f.endswith(".json.gz")),
        key=order,
    )
    names = [n for n in names if not n.startswith("to-unicode-")]
    roots: dict = {}
    entries = []
    for name in names:
        vertical, flat = leaves(name)
        own = scheme_of(name)
        best = None
        for bname, (bflat, bs) in roots.items():
            if (bs == BYTES) != (own == BYTES):
                continue
            cand = start_map(bflat, bs, own)
            sets = sorted((k, v) for k, v in flat.items() if cand.get(k) != v)
            gone = sorted((k, 0) for k in cand if k not in flat)
            cost = len(sets) + len(gone)
            if best is None or cost < best[0]:
                best = (cost, bname, bs, sets, gone)
        head = struct.pack("<B", 1 if vertical else 0)
        if best is not None and best[0] * 2 < len(flat):
            _, bname, bs, sets, gone = best
            blob = head + b"\x01" + bytes([len(bname)]) + bname.encode() + bytes([bs, own])
            blob += runs(sets, True) + runs(gone, False)
            rebuilt = start_map(roots[bname][0], bs, own)
            for k, _ in gone:
                del rebuilt[k]
            rebuilt.update(dict(sets))
            assert rebuilt == flat, name
        else:
            roots[name] = (flat, own)
            blob = head + b"\x00" + runs(sorted(flat.items()), True)
        entries.append((name, blob))
    return sorted(entries)


def umap_entries(items: list) -> bytes:
    b = bytearray(struct.pack("<I", len(items)))
    prev = 0
    for cid, s in items:
        u = s.encode("utf-8", "surrogatepass")
        assert len(u) < 256
        b += leb(cid - prev) + bytes([len(u)]) + u
        prev = cid
    return bytes(b)


def unicode_entries() -> list:
    out = []
    for f in sorted(os.listdir(SRC)):
        if not f.startswith("to-unicode-"):
            continue
        with gzip.open(os.path.join(SRC, f), "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        name = f[len("to-unicode-") : -len(".json.gz")]
        h = {int(k): v for k, v in data["CID2UNICHR_H"].items()}
        v = {int(k): x for k, x in data["CID2UNICHR_V"].items()}
        diff = sorted((k, x) for k, x in v.items() if h.get(k) != x)
        vb = bytearray(umap_entries(diff))
        gone = sorted(k for k in h if k not in v)
        vb += struct.pack("<I", len(gone))
        prev = 0
        for k in gone:
            vb += leb(k - prev)
            prev = k
        out += [(name + "/H", umap_entries(sorted(h.items()))), (name + "/V", bytes(vb))]
    return out


def container(entries: list) -> bytes:
    index = bytearray(b"ELCM" + struct.pack("<H", len(entries)))
    body = bytearray()
    for name, raw in entries:
        c = zlib.compressobj(9, zlib.DEFLATED, -15, 9)
        blob = c.compress(raw) + c.flush()
        nb = name.encode()
        index += bytes([len(nb)]) + nb + struct.pack("<II", len(body), len(blob))
        body += blob
    return bytes(index + body)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for fn, entries in (("cmaps.bin", cmap_entries()), ("unicode.bin", unicode_entries())):
        blob = container(entries)
        with open(os.path.join(OUT, fn), "wb") as fh:
            fh.write(blob)
        print(fn, len(entries), "entries,", len(blob), "bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
