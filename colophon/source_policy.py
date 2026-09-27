# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refuse TeX directives and diagram fences the worker does not render.

Checked before any compiler is started. Patterns match directives and
fences, not prose: a sentence such as "do not enable shell-escape" or
"Mermaid and D2 are not rendered" is allowed. The image has no
Asymptote, Mermaid, D2, Chromium, or Node binary, no network, and
``shell_escape = f``.
"""

import re

_WRITE18 = re.compile(r"\\write\s*18\b", re.IGNORECASE)
_SHELL = re.compile(r"\\shellescape\b", re.IGNORECASE)
# Jobs run XeLaTeX. LuaTeX is not a selectable engine, and the image does
# not build the lualatex format. \directlua is refused before compile.
_DIRECTLUA = re.compile(r"\\directlua\b", re.IGNORECASE)
_MINTED_PACKAGE = re.compile(
    r"\\usepackage\s*(?:\[[^\]]*\]\s*)?\{[^}]*\bminted\b",
    re.IGNORECASE,
)
_MINTED_USE = re.compile(
    r"\\begin\s*\{minted\}|\\(?:inputminted|newminted)\b",
    re.IGNORECASE,
)
_TIKZ_EXTERNAL = re.compile(
    r"\\(?:usetikzlibrary\s*\{[^}]*\bexternal\b|tikzexternalize|tikzsetexternalprefix)",
    re.IGNORECASE,
)
_FENCE = r"(?:`{3,}|~{3,})"
_ASYMPTOTE = re.compile(
    r"\\usepackage\s*(?:\[[^\]]*\]\s*)?\{[^}]*\basymptote\b"
    r"|\\begin\s*\{(?:asy|asymptote)\}"
    r"|" + _FENCE + r"[ \t]*(?:\.?(?:asymptote|asy)\b|\{\s*\.?(?:asymptote|asy)\b)",
    re.IGNORECASE,
)
_MERMAID = re.compile(
    _FENCE + r"[ \t]*(?:\.?mermaid\b|\{\s*\.?mermaid\b)",
    re.IGNORECASE,
)
_D2 = re.compile(
    _FENCE + r"[ \t]*(?:\.?d2\b|\{\s*\.?d2\b)",
    re.IGNORECASE,
)
_GNUPLOT = re.compile(
    r"\\usepackage\s*(?:\[[^\]]*\]\s*)?\{[^}]*\b(?:gnuplottex|gnuplot)\b"
    r"|\\begin\s*\{gnuplot\}"
    r"|\\gnuplot\b",
    re.IGNORECASE,
)
_EPSTOPDF = re.compile(
    r"\\usepackage\s*(?:\[[^\]]*\]\s*)?\{[^}]*\bepstopdf\b"
    r"|\\epstopdf(?:setup|call)?\b",
    re.IGNORECASE,
)
_SVG = re.compile(
    r"\\usepackage\s*(?:\[[^\]]*\]\s*)?\{[^}]*\bsvg\b"
    r"|\\includesvg\b"
    r"|\\svgsetup\b",
    re.IGNORECASE,
)
# Automatic tikz-feynman layout needs LuaLaTeX. \diagram* and \vertex stay.
_FEYNMAN_AUTO = re.compile(
    r"\\feynmandiagram\b|\\diagram(?!\*)",
    re.IGNORECASE,
)
# \@@input is the primitive. \include does not match \includegraphics.
# A letter would continue the command (\includegraphics, \inputiffileexists).
# A digit does not: \openin4 is the primitive stream form.
_FILE_READ = re.compile(
    r"\\(?P<cmd>@@input|input|include|openin)(?![A-Za-z@])",
    re.IGNORECASE,
)
_TIKZ_FENCE = re.compile(
    r"(?m)^[ ]{0,3}(?:`{3,}|~{3,})[ \t]*(?:tikz\b|\.tikz\b|\{\.?tikz\b)"
)


def _argument_path(source, start, command):
    """Filename after ``\\input``, ``\\include``, or ``\\openin``."""
    index = start
    length = len(source)
    while index < length and source[index] in " \t\r\n":
        index += 1
    if command.lower() == "openin":
        if index < length and source[index] == "\\":
            index += 1
            while index < length and (source[index].isalpha() or source[index] == "@"):
                index += 1
        else:
            while index < length and source[index].isdigit():
                index += 1
        while index < length and source[index] in " \t\r\n":
            index += 1
        if index < length and source[index] == "=":
            index += 1
            while index < length and source[index] in " \t\r\n":
                index += 1
    if index >= length:
        return ""
    if source[index] == "{":
        depth = 1
        index += 1
        begin = index
        while index < length and depth:
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
            index += 1
        return source[begin : index - 1 if depth == 0 else index]
    if source[index] == '"':
        end = source.find('"', index + 1)
        if end == -1:
            return source[index + 1 :]
        return source[index + 1 : end]
    end = index
    while end < length and source[end] not in " \t\r\n%":
        end += 1
    return source[index:end]


def _path_escapes(name):
    """True for an absolute path or any ``..`` segment."""
    text = name.strip()
    if text.startswith("/") or text.startswith("\\"):
        return True
    return any(part == ".." for part in text.replace("\\", "/").split("/"))


def reject_forbidden_source(source):
    """Raise ``JobRejected`` when the source asks for a forbidden tool."""
    from colophon.enums import JobRejected
    from colophon.limits import MAX_FENCES_PER_JOB

    if not isinstance(source, str):
        raise JobRejected("body")
    if _WRITE18.search(source):
        raise JobRejected("write18")
    if _SHELL.search(source):
        raise JobRejected("shell-escape")
    if _DIRECTLUA.search(source):
        raise JobRejected("directlua")
    if _MINTED_PACKAGE.search(source) or _MINTED_USE.search(source):
        raise JobRejected("minted")
    if _TIKZ_EXTERNAL.search(source):
        raise JobRejected("tikz-external")
    if _ASYMPTOTE.search(source):
        raise JobRejected("asymptote")
    if _MERMAID.search(source):
        raise JobRejected("mermaid")
    if _D2.search(source):
        raise JobRejected("d2")
    if _GNUPLOT.search(source):
        raise JobRejected("gnuplot")
    if _EPSTOPDF.search(source):
        raise JobRejected("epstopdf")
    if _SVG.search(source):
        raise JobRejected("svg")
    if _FEYNMAN_AUTO.search(source):
        raise JobRejected("feynman-auto")
    for match in _FILE_READ.finditer(source):
        if _path_escapes(_argument_path(source, match.end(), match.group("cmd"))):
            raise JobRejected("openin")
    if len(_TIKZ_FENCE.findall(source)) > MAX_FENCES_PER_JOB:
        raise JobRejected("fences")
