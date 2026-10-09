# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R59-OVERHANG. A picture wider than its text line is a job warning.

endleaf-fit.tex logs ``ENDLEAF_WIDE_PICTURE width=..pt line=..pt`` for a
plain TikZ picture and ``ENDLEAF_OVERHANG package=sysml-tikz width=..pt
line=..pt`` for a fitted canvas. The sandbox turns those lines into one
``ENDLEAF_LAYOUT`` stderr line; the runner reads it back; the job record
carries it in ``warnings`` beside ``notationPdfOnly``. It is a warning: the
PDF is still returned.
"""

import json
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
# Below this the picture only touches the margin; TeX's own overfull
# warning is the signal for that, not this one.
MIN_OVERHANG_PT = 1.0


def layout_warnings(log):
    """Structured warnings from a final-pass log; ``[]`` when nothing overhangs."""
    text = (log or "").replace("\n", "")
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
                clean.append(
                    {
                        "code": LAYOUT_CODE,
                        "packages": list(item["packages"]),
                        "message": item["message"],
                    }
                )
        return clean
    return []
