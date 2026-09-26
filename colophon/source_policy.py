# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refuse TeX directives that need shell escape or an outside program.

Checked before any compiler is started. Patterns match directives, not
prose: a sentence such as "do not enable shell-escape" is allowed.
The image also has no Asymptote binary, no network, and ``shell_escape = f``.
"""

import re

_WRITE18 = re.compile(r"\\write\s*18\b", re.IGNORECASE)
_SHELL = re.compile(r"\\shellescape\b", re.IGNORECASE)
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
_ASYMPTOTE = re.compile(
    r"\\usepackage\s*(?:\[[^\]]*\]\s*)?\{[^}]*\basymptote\b"
    r"|\\begin\s*\{(?:asy|asymptote)\}"
    r"|```+\s*\{?\.?\s*(?:asymptote|asy)\b",
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
    if _MINTED_PACKAGE.search(source) or _MINTED_USE.search(source):
        raise JobRejected("minted")
    if _TIKZ_EXTERNAL.search(source):
        raise JobRejected("tikz-external")
    if _ASYMPTOTE.search(source):
        raise JobRejected("asymptote")
    if _GNUPLOT.search(source):
        raise JobRejected("gnuplot")
    if _EPSTOPDF.search(source):
        raise JobRejected("epstopdf")
    if _SVG.search(source):
        raise JobRejected("svg")
    if _FEYNMAN_AUTO.search(source):
        raise JobRejected("feynman-auto")
