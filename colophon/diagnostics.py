# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured render errors. No shell."""

import json
import re
from pathlib import Path

_TEX_LINE = re.compile(r"^(.+?):(\d+):\s+(.+)$", re.MULTILINE)
_LINE_IN_MESSAGE = re.compile(r"\bline\s+(\d+)\b", re.IGNORECASE)


# TeX breaks log lines at max_print_line (79). A longer error message
# continues on the next line; join it so errorText is the whole line.
_TEX_WRAP = 79


def _unwrap(text):
    pieces = []
    pending = ""
    for line in text.splitlines():
        pending = pending + line if pending else line
        if len(line) != _TEX_WRAP:
            pieces.append(pending)
            pending = ""
    if pending:
        pieces.append(pending)
    return "\n".join(pieces)


def first_tex_error(text):
    """Return the first TeX file:line error, or ``None``."""
    if not text:
        return None
    for match in _TEX_LINE.finditer(_unwrap(text)):
        message = match.group(3).strip()
        if "Warning" in message:
            continue
        return {
            "engine": "tex",
            "message": message[:400],
            "file": Path(match.group(1)).name,
            "line": int(match.group(2)),
            "fence": None,
        }
    return None


def _fill_line(diagnostic):
    if not isinstance(diagnostic, dict):
        return None
    message = diagnostic.get("message") or ""
    if diagnostic.get("line") is None:
        found = _LINE_IN_MESSAGE.search(message)
        if found:
            diagnostic["line"] = int(found.group(1))
    diagnostic.setdefault("file", None)
    diagnostic.setdefault("fence", None)
    diagnostic.setdefault("engine", None)
    diagnostic["message"] = str(message)[:400]
    return diagnostic


def parse_stderr(stderr):
    """Read ``ENDLEAF_METERS`` and the first ``ENDLEAF_DIAG`` line."""
    meters = {"memoryPeak": None, "pidsPeak": None}
    diagnostic = None
    if not stderr:
        return meters, diagnostic
    text = stderr.decode("utf-8", "replace")
    for line in text.splitlines():
        if line.startswith("ENDLEAF_METERS "):
            try:
                parsed = json.loads(line.split(" ", 1)[1])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                meters["memoryPeak"] = parsed.get("memoryPeak")
                meters["pidsPeak"] = parsed.get("pidsPeak")
                mode = parsed.get("memoryMode")
                if mode in ("cgroup", "rlimit"):
                    meters["memoryMode"] = mode
        elif line.startswith("ENDLEAF_DIAG ") and diagnostic is None:
            try:
                parsed = json.loads(line.split(" ", 1)[1])
            except json.JSONDecodeError:
                continue
            diagnostic = _fill_line(parsed)
    if diagnostic is None:
        diagnostic = first_tex_error(text)
    return meters, diagnostic
