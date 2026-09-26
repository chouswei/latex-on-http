# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refuse inputs that need shell escape or an outside program.

Checked before any compiler is started. The image also has no Asymptote
binary, no network, and ``shell_escape = f``.
"""

import re

_WRITE18 = re.compile(r"\\write\s*18\b", re.IGNORECASE)
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
_SHELL = re.compile(
    r"(?<!no-)shell-escape|shell_escape|enable[-_]write18",
    re.IGNORECASE,
)


def reject_forbidden_source(source):
    """Raise ``JobRejected`` when the source asks for a forbidden tool."""
    from colophon.enums import JobRejected

    if not isinstance(source, str):
        raise JobRejected("input")
    stripped = re.sub(r"-no-shell-escape", "", source, flags=re.IGNORECASE)
    if _SHELL.search(stripped):
        raise JobRejected("shell-escape")
    if _WRITE18.search(source):
        raise JobRejected("write18")
    if _MINTED_PACKAGE.search(source) or _MINTED_USE.search(source):
        raise JobRejected("minted")
    if _TIKZ_EXTERNAL.search(source):
        raise JobRejected("tikz-external")
    if _ASYMPTOTE.search(source):
        raise JobRejected("asymptote")
