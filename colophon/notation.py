# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inline siunitx and mhchem are PDF only.

HTML and DOCX keep the command source as literal text and report
``notationPdfOnly``. Fenced diagrams are left alone so the diagram
filter can still turn them into images. PDF is unchanged.
"""

import re

_MESSAGE = (
    "Inline siunitx and mhchem notation is PDF only. "
    "HTML and DOCX keep the source text."
)

_SIUNITX = {
    "qty",
    "qtylist",
    "qtyproduct",
    "qtyrange",
    "si",
    "SI",
    "num",
    "numlist",
    "numproduct",
    "numrange",
    "unit",
    "ang",
    "complexnum",
    "complexqty",
    "SIlist",
    "SIrange",
}
_MHCHEM = {"ce", "bond", "mhchem"}
_NAMES = sorted(_SIUNITX | _MHCHEM, key=len, reverse=True)
_CMD = re.compile(
    r"\\(" + "|".join(_NAMES) + r")\*?(?![A-Za-z@])"
)
_FENCE = re.compile(
    r"(?ms)^[ ]{0,3}(`{3,}|~{3,})[^\n]*\n.*?^[ ]{0,3}\1[ ]*$"
)


def _package(name):
    if name in _MHCHEM:
        return "mhchem"
    return "siunitx"


def _protected_spans(source, input_kind):
    if input_kind != "markdown":
        return []
    spans = [(match.start(), match.end()) for match in _FENCE.finditer(source)]

    def inside(index):
        return any(start <= index < end for start, end in spans)

    index = 0
    while index < len(source):
        if source[index] != "`" or inside(index):
            index += 1
            continue
        width = 1
        while index + width < len(source) and source[index + width] == "`":
            width += 1
        close = source.find("`" * width, index + width)
        if close == -1:
            break
        spans.append((index, close + width))
        index = close + width
    return spans


def _consume_group(text, index, open_ch, close_ch):
    if index >= len(text) or text[index] != open_ch:
        return index
    depth = 0
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        char = text[index]
        if char == open_ch:
            depth += 1
        elif char == close_ch:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


def _command_end(text, index):
    while index < len(text):
        cursor = index
        while cursor < len(text) and text[cursor] in " \t\n":
            cursor += 1
        if cursor >= len(text) or text[cursor] not in "[{":
            break
        closer = "]" if text[cursor] == "[" else "}"
        index = _consume_group(text, cursor, text[cursor], closer)
    return index


def _commands(source, input_kind):
    protected = _protected_spans(source, input_kind)

    def inside(index):
        return any(start <= index < end for start, end in protected)

    found = []
    cursor = 0
    while True:
        match = _CMD.search(source, cursor)
        if match is None:
            return found
        if inside(match.start()):
            cursor = match.end()
            continue
        end = _command_end(source, match.end())
        found.append((match.start(), end, _package(match.group(1))))
        cursor = end


def _markdown_literal(text):
    ticks = "`"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{text}{ticks}"


def _tex_literal(text):
    if "\n" in text:
        return text
    for delim in "|!/#~":
        if delim not in text:
            return f"\\verb{delim}{text}{delim}"
    return text


def notation_warnings(source, input_kind, output_format):
    """Structured warning for HTML or DOCX. PDF returns an empty list."""
    if output_format not in ("html", "docx"):
        return []
    packages = sorted({item[2] for item in _commands(source, input_kind)})
    if not packages:
        return []
    return [
        {
            "code": "notationPdfOnly",
            "packages": packages,
            "message": _MESSAGE,
        }
    ]


def degrade_inline_notation(source, input_kind, output_format):
    """Leave PDF source unchanged. HTML and DOCX keep the command text."""
    if output_format not in ("html", "docx"):
        return source
    found = _commands(source, input_kind)
    if not found:
        return source
    literal = _tex_literal if input_kind == "tex" else _markdown_literal
    parts = []
    cursor = 0
    for start, end, _package_name in found:
        parts.append(source[cursor:start])
        parts.append(literal(source[start:end]))
        cursor = end
    parts.append(source[cursor:])
    return "".join(parts)
