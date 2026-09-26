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


def reject_forbidden_source(source):
    """Raise ``JobRejected`` when the source asks for a forbidden tool."""
    from colophon.enums import JobRejected

    if not isinstance(source, str):
        raise JobRejected("input")
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
