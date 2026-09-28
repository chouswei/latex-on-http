# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load endleaf-floorplan.sty. LaTeX forbids \\newcommand names that start with \\end."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.templates import compose, example_body

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"
_TEXINPUTS = os.pathsep.join(
    (
        str(_ROOT / "colophon/share/tex/latex/colophon-v1"),
        str(_ROOT / "colophon/share/tex/latex/endleaf-floorplan"),
        str(_ROOT / "colophon/share/tex/latex/sysml-tikz"),
        str(_ROOT / "vendor/pidcircuittikz"),
        "",
    )
)
_ENGINE = (
    shutil.which("xelatex") or shutil.which("lualatex") or shutil.which("pdflatex")
)
_LANES = ("InstruMeasure", "Weft", "Investor")

# A definition whose control sequence starts with \end (lowercase). LaTeX's
# \@ifdefinable rejects those three letters. \EndleafLane is a different name.
_ILLEGAL_DEF = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?"
    r"\s*\{\\end"
    r"|\\(?:NewDocumentCommand|RenewDocumentCommand|DeclareDocumentCommand)"
    r"\s*\{\\end"
    r"|\\(?:e|g|x)?def\\end[A-Za-z@]"
)

_MINIMAL = r"""
\documentclass{article}
\usepackage{endleaf-floorplan}
\begin{document}
\begin{tikzpicture}[/floorplan/plan-scale=500]
  \draw[floorplan wall] (0,0) -- (4,0) -- (4,3) -- (0,3) -- cycle;
  \tikzset{floorplan door={(0.4,0)}{(1.3,0)}}
  \tikzset{floorplan window={(1.6,3)}{(2.6,3)}}
  \node at (2,1.5) [floorplan room label={Room}{(0,0)}{(4,3)}];
  \tikzset{floorplan dimension={(0,-0.6)}{(4,-0.6)}}
  \begin{scope}[shift={(0,-1.6)}]
    \tikzset{floorplan scale bar}
  \end{scope}
  \begin{scope}[shift={(5,2)}]
    \tikzset{floorplan north arrow}
  \end{scope}
\end{tikzpicture}
\end{document}
"""

_SCAN_SUFFIXES = {
    ".sty",
    ".tex",
    ".latex",
    ".cls",
    ".dtx",
    ".ltx",
    ".def",
    ".lua",
    ".py",
    ".md",
    ".html",
    ".sh",
    ".yml",
}


def _sources():
    skip = {".git", ".venv", ".pytest_cache", "__pycache__"}
    for path in _ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in _SCAN_SUFFIXES:
            continue
        if skip.intersection(path.parts):
            continue
        yield path


def test_no_defined_control_sequence_starts_with_end():
    hits = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if _ILLEGAL_DEF.search(line):
                hits.append(f"{path.relative_to(_ROOT)}:{number}:{line.strip()}")
    assert hits == []


def _prepare(tex):
    """Drop xeCJK lines when that package or the CJK font is not installed.

    The style under test is endleaf-floorplan. The font lines are not it.
    """
    if shutil.which("kpsewhich") is None:
        return tex
    found = subprocess.run(
        ["kpsewhich", "xeCJK.sty"],
        check=False,
        capture_output=True,
    )
    if found.returncode != 0 or not _cjk_font_installed():
        tex = (
            tex.replace("\\usepackage{fontspec}\n", "")
            .replace("\\usepackage{xeCJK}\n", "")
            .replace("\\setCJKmainfont{Noto Sans CJK TC}\n", "")
        )
    return tex


def _cjk_font_installed():
    fc_list = shutil.which("fc-list")
    if fc_list is None:
        return False
    completed = subprocess.run(
        [fc_list, ":family"],
        check=False,
        capture_output=True,
        text=True,
    )
    return "Noto Sans CJK TC" in completed.stdout


def _compile(tmp_path, tex, name):
    (tmp_path / f"{name}.tex").write_text(tex, encoding="utf-8")
    env = os.environ.copy()
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    completed = subprocess.run(
        [
            _ENGINE,
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-cnf-line=openin_any=p",
            f"{name}.tex",
        ],
        cwd=tmp_path,
        check=False,
        timeout=120,
        capture_output=True,
        env=env,
    )
    log_path = tmp_path / f"{name}.log"
    log = (
        log_path.read_text(encoding="utf-8", errors="replace")
        if log_path.is_file()
        else completed.stdout.decode("utf-8", "replace")
    )
    assert completed.returncode == 0, log[-1500:]
    assert (tmp_path / f"{name}.pdf").is_file()
    assert "endleaf-floorplan.sty" in log
    assert "Or name \\end" not in log


@pytest.mark.skipif(_ENGINE is None, reason="TeX is not installed")
def test_endleaf_floorplan_sty_and_templates_load(tmp_path):
    """Minimal document, then the floorplan template for each lane."""
    preamble = (
        _ROOT / "colophon/share/tex/latex/colophon-v1/colophon-v1-preamble.tex"
    ).read_text(encoding="utf-8")
    assert "\\usepackage{endleaf-floorplan}" in preamble
    _compile(tmp_path, _MINIMAL, "minimal")
    sample = example_body("floorplan", _OWNED)
    for lane in _LANES:
        tex = _prepare(compose("floorplan", lane, sample, _OWNED))
        assert f"\\newcommand{{\\EndleafLane}}{{{lane}}}" in tex
        _compile(tmp_path, tex, f"floorplan-{lane}")
