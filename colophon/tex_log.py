# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""TeX log warning counts and a typed first-error cause. No shell.

ENDLEAF-R57-WARN and ENDLEAF-R57-CAUSE (Endleaf requirements). Only
integer counts and a short cause code leave the sandbox, never log text.

The cause table is written in Endleaf's own words. The choice of
patterns is adapted from ``latex-rescue/references/error-catalog.md`` in
awesome-latex-skills, Copyright (c) 2026 awesome-latex-skills
contributors, MIT License (see NOTICE). Only the most common patterns
that a body-only Endleaf job can hit are kept.
"""

import json
import re

TEX_WARN_PREFIX = "ENDLEAF_TEXWARN "
TEX_WARN_KEYS = ("overfull", "underfull", "undefinedRef", "undefinedCite")

# Box warnings start a log line. A reference or citation warning starts
# with the key in quotes; the line may wrap later, never in this prefix.
_COUNTERS = (
    ("overfull", re.compile(r"^Overfull \\[hv]box", re.MULTILINE)),
    ("underfull", re.compile(r"^Underfull \\[hv]box", re.MULTILINE)),
    ("undefinedRef", re.compile(r"^LaTeX Warning: Reference [`'\u2018]", re.MULTILINE)),
    ("undefinedCite", re.compile(r"^LaTeX Warning: Citation [`'\u2018]", re.MULTILINE)),
)

# First match wins. Codes are stable API: the gate maps each to a fix.
CAUSES = (
    ("preambleOnly", re.compile(r"Can be used only in preamble")),
    ("undefinedEnvironment", re.compile(r"Environment \S+ undefined")),
    ("environmentMismatch", re.compile(r"\\begin\{[^}]*\} on input line \d+ ended by")),
    ("undefinedCommand", re.compile(r"Undefined control sequence")),
    (
        "mathMode",
        re.compile(
            r"Missing \$ inserted|Double (?:sub|super)script|allowed only in math mode"
        ),
    ),
    (
        "braces",
        re.compile(r"Missing [{}] inserted|Extra \}, or forgotten|Too many \}'s"),
    ),
    (
        "unclosedArgument",
        re.compile(
            r"Paragraph ended before .+? was complete|Runaway argument"
            r"|File ended while scanning"
        ),
    ),
    ("tableColumns", re.compile(r"Extra alignment tab")),
    ("tableRule", re.compile(r"Misplaced \\(?:noalign|hline)")),
    ("lineBreak", re.compile(r"There's no line here to end")),
    ("fileNotFound", re.compile(r"File [`'\u2018][^'\u2019]*['\u2019] not found")),
)
CAUSE_CODES = tuple(code for code, _pattern in CAUSES)


def count_tex_warnings(log):
    """Counts for the four keys. ``log`` is the final pass's log text."""
    text = log or ""
    return {key: len(pattern.findall(text)) for key, pattern in _COUNTERS}


def any_tex_warning(counts):
    return isinstance(counts, dict) and any(
        isinstance(counts.get(key), int) and counts.get(key) > 0
        for key in TEX_WARN_KEYS
    )


def tex_warn_line(counts):
    """One stderr line, or ``None`` when every count is zero."""
    if not any_tex_warning(counts):
        return None
    payload = {key: int(counts.get(key) or 0) for key in TEX_WARN_KEYS}
    return TEX_WARN_PREFIX + json.dumps(payload, separators=(",", ":"))


def parse_tex_warnings(stderr):
    """Read the first ``ENDLEAF_TEXWARN`` line; ``None`` when absent or all zero."""
    if not stderr:
        return None
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    for line in text.splitlines():
        if not line.startswith(TEX_WARN_PREFIX):
            continue
        try:
            parsed = json.loads(line[len(TEX_WARN_PREFIX) :])
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        counts = {}
        for key in TEX_WARN_KEYS:
            value = parsed.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return None
            counts[key] = value
        return counts if any_tex_warning(counts) else None
    return None


def error_cause(message):
    """Cause code for a first TeX diagnostic message, or ``None``."""
    if not isinstance(message, str) or not message:
        return None
    for code, pattern in CAUSES:
        if pattern.search(message):
            return code
    return None
