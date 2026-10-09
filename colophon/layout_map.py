# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R60-LAYOUT. The page layout map of a fulldoc render.

endleaf-layout.tex logs, in the final pass:
  ENDLEAF_GEOM <paperheight>pt <texttop>pt <textheight>pt <linewidth>pt
  ENDLEAF_PICBOX <id> <width>pt <height>pt     (a picture inside a float)
  ENDLEAF_MARK <id> <tag> <page> <ypos-sp> <portrait|landscape>
The gate puts the marks in the body (\\EndleafMark{id}{tag}); the worker
only reads them back. The sandbox turns them into one ``ENDLEAF_LAYOUTMAP``
stderr line (zlib, then base64url, of compact JSON); the runner reads it
back; the response carries it in the ``X-Endleaf-Layout`` header. The map
holds ids, tags, page numbers and positions only: never document text.
A map over the size cap is dropped (the PDF is still returned).
"""

import base64
import json
import re
import zlib

LAYOUT_MAP_PREFIX = "ENDLEAF_LAYOUTMAP "
LAYOUT_HEADER = "X-Endleaf-Layout"
LAYOUT_MAP_VERSION = 1
# Response headers share a 16 KiB budget in common HTTP clients.
LAYOUT_MAP_CAP_BYTES = 12000
_SP_PER_PT = 65536.0
_ID = r"[A-Za-z0-9:._\-/+]{1,80}"
_PT = r"(-?[0-9]+(?:\.[0-9]+)?)pt"
_GEOM = re.compile(r"ENDLEAF_GEOM " + _PT + " " + _PT + " " + _PT + " " + _PT)
_PICBOX = re.compile(r"ENDLEAF_PICBOX (" + _ID + ") " + _PT + " " + _PT)
_MARK = re.compile(
    r"ENDLEAF_MARK (" + _ID + r") ([ser]) ([0-9]{1,5}) (-?[0-9]{1,12}) (portrait|landscape)"
)


def _pt(value):
    return round(float(value), 1)


def layout_map(log):
    """The map from a final-pass log, or ``None`` when the body had no marks."""
    # TeX wraps log lines at 79 characters; read the log with breaks removed
    # and match on the keywords, as layout_warn does.
    text = (log or "").replace("\n", "")
    geom = _GEOM.search(text)
    marks = []
    for match in _MARK.finditer(text):
        marks.append(
            [
                match.group(1),
                match.group(2),
                int(match.group(3)),
                round(int(match.group(4)) / _SP_PER_PT, 1),
                "l" if match.group(5) == "landscape" else "p",
            ]
        )
    if geom is None or not marks:
        return None
    pictures = []
    seen = set()
    for match in _PICBOX.finditer(text):
        if match.group(1) in seen:
            continue
        seen.add(match.group(1))
        pictures.append([match.group(1), _pt(match.group(2)), _pt(match.group(3))])
    return {
        "v": LAYOUT_MAP_VERSION,
        "geom": {
            "paper": _pt(geom.group(1)),
            "top": _pt(geom.group(2)),
            "textHeight": _pt(geom.group(3)),
            "line": _pt(geom.group(4)),
        },
        "marks": marks,
        "pictures": pictures,
    }


def encode_map(mapping, cap=LAYOUT_MAP_CAP_BYTES):
    """base64url(zlib(json)), or ``None`` when absent or over the cap."""
    if not mapping:
        return None
    raw = json.dumps(mapping, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")
    if len(encoded) > cap:
        return None
    return encoded


def layout_map_line(log):
    """One stderr line, or ``None``."""
    encoded = encode_map(layout_map(log))
    return None if encoded is None else LAYOUT_MAP_PREFIX + encoded


def parse_layout_map(stderr):
    """The encoded map from the sandbox's stderr, re-checked; ``None`` when absent or malformed."""
    if not stderr:
        return None
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    for line in text.splitlines():
        if not line.startswith(LAYOUT_MAP_PREFIX):
            continue
        encoded = line[len(LAYOUT_MAP_PREFIX) :].strip()
        if not encoded or len(encoded) > LAYOUT_MAP_CAP_BYTES:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_\-=]+", encoded):
            return None
        try:
            decoded = json.loads(zlib.decompress(base64.urlsafe_b64decode(encoded), bufsize=1 << 16))
        except (ValueError, zlib.error):
            return None
        if not isinstance(decoded, dict) or decoded.get("v") != LAYOUT_MAP_VERSION:
            return None
        return encoded
    return None


def decode_map(encoded):
    """The gate side of the format, kept here so both ends share one test."""
    return json.loads(zlib.decompress(base64.urlsafe_b64decode(encoded)))
