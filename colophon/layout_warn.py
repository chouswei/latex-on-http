# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R59-OVERHANG. A picture wider than its text line is a job warning.

endleaf-fit.tex logs ``ENDLEAF_WIDE_PICTURE width=..pt line=..pt`` for a
plain TikZ picture and ``ENDLEAF_OVERHANG package=sysml-tikz width=..pt
line=..pt`` for a fitted canvas. The sandbox turns those lines into one
``ENDLEAF_LAYOUT`` stderr line; the runner reads it back; the job record
carries it in ``warnings`` beside ``notationPdfOnly``. It is a warning: the
PDF is still returned.

ENDLEAF-R61-FIT. In fulldoc, endleaf-layout.tex also logs every picture as
``ENDLEAF_PICFIT id plain|sysml width line minsize``: its part id (the last
layout mark), the line it must fit and the smallest text size set inside
it. Then each picture past its line is its own warning and carries
``partId``, ``overMm``, ``scaleToFit`` (line / width, rounded down to two
decimals so the scaled picture fits), ``minTextPt`` (the smallest text at
that scale) and ``belowTypeFloor`` (``minTextPt`` under 7 pt, ENDLEAF-R26),
with a ``fix``: scale inside the source when the text stays at or above
7 pt, otherwise redraw or split. At most ``MAX_PICTURE_WARNINGS`` pictures
are listed; one more item counts the rest.
"""

import json
import math
import re

LAYOUT_PREFIX = "ENDLEAF_LAYOUT "
LAYOUT_CODE = "layout_overhang"
_PT_TO_MM = 25.4 / 72.27
# TeX wraps log lines at 79 characters, so the log is read with line
# breaks removed. The pattern is anchored on its own keywords.
_LINE = re.compile(
    r"ENDLEAF_(WIDE_PICTURE|OVERHANG)(?: package=([A-Za-z-]+))?"
    r" width=([0-9]+(?:\.[0-9]+)?)pt line=([0-9]+(?:\.[0-9]+)?)pt"
)
_FIT = re.compile(
    r"ENDLEAF_PICFIT (\S{1,80}) (plain|sysml) ([0-9]+(?:\.[0-9]+)?)pt"
    r" ([0-9]+(?:\.[0-9]+)?)pt ([0-9]+(?:\.[0-9]+)?)"
)
TYPE_FLOOR_PT = 7.0
# endleaf-layout.tex logs 99 when a picture sets no text.
NO_TEXT_PT = 99.0
MAX_PICTURE_WARNINGS = 10
# Below this the picture only touches the margin; TeX's own overfull
# warning is the signal for that, not this one.
MIN_OVERHANG_PT = 1.0


def picture_fit(width_pt, line_pt, min_size_pt):
    """(scaleToFit, minTextPt, belowTypeFloor) for a picture wider than its line."""
    scale = math.floor(line_pt / width_pt * 100) / 100
    if min_size_pt >= NO_TEXT_PT:
        return scale, None, False
    min_text = math.floor(min_size_pt * scale * 10) / 10
    return scale, min_text, min_text < TYPE_FLOOR_PT


def _picture_warnings(text):
    out = []
    extra = 0
    for match in _FIT.finditer(text):
        where, kind = match.group(1), match.group(2)
        width, line, size = (float(match.group(n)) for n in (3, 4, 5))
        over = width - line
        if over < MIN_OVERHANG_PT or width <= 0:
            continue
        if len(out) >= MAX_PICTURE_WARNINGS:
            extra += 1
            continue
        scale, min_text, below = picture_fit(width, line, size)
        millimetres = round(over * _PT_TO_MM, 1)
        if below:
            fix = f"redraw or split; scaling would put text at {min_text:g} pt"
        else:
            fix = f"scale inside the source to {scale:.2f}"
        part = None if where == "-" else where
        item = {
            "code": LAYOUT_CODE,
            "packages": ["sysml-tikz" if kind == "sysml" else "tikz"],
            "message": (
                (f"{part}: " if part else "")
                + f"a picture runs {millimetres:.1f} mm past the text line; "
                + f"scaleToFit {scale:.2f}, "
                + (f"minTextPt {min_text:g}" if min_text is not None else "no text")
                + (" (below 7 pt)" if below else "")
                + f". Fix: {fix}"
            ),
            "overMm": millimetres,
            "scaleToFit": scale,
            **({"minTextPt": min_text} if min_text is not None else {}),
            "belowTypeFloor": below,
            "fix": fix,
        }
        if part:
            item["partId"] = part
        out.append(item)
    if extra:
        out.append(
            {
                "code": LAYOUT_CODE,
                "packages": ["tikz"],
                "message": f"{extra} more pictures run past the text line",
            }
        )
    return out


def layout_warnings(log):
    """Structured warnings from a final-pass log; ``[]`` when nothing overhangs."""
    text = (log or "").replace("\n", "")
    if "ENDLEAF_PICFIT" in text:
        return _picture_warnings(text)
    worst = {}
    counts = {}
    for match in _LINE.finditer(text):
        package = match.group(2) or "tikz"
        over = float(match.group(3)) - float(match.group(4))
        if over < MIN_OVERHANG_PT:
            continue
        counts[package] = counts.get(package, 0) + 1
        worst[package] = max(worst.get(package, 0.0), over)
    out = []
    for package in sorted(worst):
        millimetres = worst[package] * _PT_TO_MM
        count = counts[package]
        noun = "picture runs" if count == 1 else f"{count} pictures run up to"
        out.append(
            {
                "code": LAYOUT_CODE,
                "packages": [package],
                "message": (
                    f"a {noun} {millimetres:.1f} mm past the text line; "
                    "narrow or split the picture"
                ),
            }
        )
    return out


def layout_line(warnings):
    """One stderr line, or ``None`` when there is nothing to report."""
    if not warnings:
        return None
    return LAYOUT_PREFIX + json.dumps(warnings, separators=(",", ":"))


_FIT_KEYS = {
    "partId": str,
    "overMm": (int, float),
    "scaleToFit": (int, float),
    "minTextPt": (int, float),
    "belowTypeFloor": bool,
    "fix": str,
}


def parse_layout(stderr):
    """Read the ``ENDLEAF_LAYOUT`` line back; ``[]`` when absent or malformed."""
    if not stderr:
        return []
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    for line in text.splitlines():
        if not line.startswith(LAYOUT_PREFIX):
            continue
        try:
            parsed = json.loads(line[len(LAYOUT_PREFIX) :])
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        clean = []
        for item in parsed:
            if (
                isinstance(item, dict)
                and item.get("code") == LAYOUT_CODE
                and isinstance(item.get("packages"), list)
                and item["packages"]
                and all(isinstance(name, str) and name for name in item["packages"])
                and isinstance(item.get("message"), str)
                and item["message"]
            ):
                kept = {
                    "code": LAYOUT_CODE,
                    "packages": list(item["packages"]),
                    "message": item["message"],
                }
                for key in _FIT_KEYS:
                    if key in item and isinstance(item[key], _FIT_KEYS[key]):
                        kept[key] = item[key]
                clean.append(kept)
        return clean
    return []
