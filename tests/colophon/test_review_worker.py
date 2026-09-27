# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Playbook-review worker fixes: fence CJK, dimension labels, PID pos."""

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
        str(_ROOT / "colophon/share/tex/latex/colophon-floorplan"),
        str(_ROOT / "vendor/pidcircuittikz"),
        "",
    )
)
_XELATEX = shutil.which("xelatex")
_PDFTOTEXT = shutil.which("pdftotext")
_PDFFONTS = shutil.which("pdffonts")


def _compile(tmp_path, tex):
    (tmp_path / "job.tex").write_text(tex, encoding="utf-8")
    env = os.environ.copy()
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    completed = subprocess.run(
        [
            "xelatex",
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-cnf-line=openin_any=p",
            "job.tex",
        ],
        cwd=tmp_path,
        check=False,
        timeout=60,
        capture_output=True,
        env=env,
    )
    log = (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")
    assert completed.returncode == 0, log[-1200:]
    return tmp_path / "job.pdf"


def _text(pdf):
    completed = subprocess.run(
        ["pdftotext", "-raw", str(pdf), "-"],
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    return completed.stdout.decode("utf-8", "replace")


@pytest.mark.skipif(_XELATEX is None, reason="xelatex is not installed")
def test_openin_any_p_refuses_hostname(tmp_path):
    tex = tmp_path / "job.tex"
    tex.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\input{/etc/hostname}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            "xelatex",
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-cnf-line=openin_any=p",
            "job.tex",
        ],
        cwd=tmp_path,
        check=False,
        timeout=60,
        capture_output=True,
    )
    assert completed.returncode != 0
    if (tmp_path / "job.pdf").is_file() and _PDFTOTEXT:
        assert "hostname" not in _text(tmp_path / "job.pdf").lower()


@pytest.mark.skipif(
    _XELATEX is None or _PDFTOTEXT is None, reason="poppler or xelatex missing"
)
def test_three_metre_wall_reads_three_metres(tmp_path):
    sample = example_body("floorplan", _OWNED)
    tex = compose("floorplan", "InstruMeasure", sample, _OWNED)
    pdf = _compile(tmp_path, tex)
    text = _text(pdf)
    assert "3.00 m" in text
    assert "4.00 m" in text
    assert "2.99" not in text
    assert text.count("1 m") == 1
    half = (_ROOT / "tests/colophon/fixtures/kinds/floorplan.tex").read_text(
        encoding="utf-8"
    )
    half_dir = tmp_path / "half"
    half_dir.mkdir()
    half_pdf = _compile(half_dir, compose("floorplan", "Weft", half, _OWNED))
    half_text = _text(half_pdf)
    assert "2.00 m" in half_text
    assert "1.50 m" in half_text


@pytest.mark.skipif(
    _XELATEX is None or _PDFTOTEXT is None, reason="poppler or xelatex missing"
)
def test_scale_bar_pic_draws_once(tmp_path):
    body = (
        "\\begin{tikzpicture}[/floorplan/plan-scale=1000]\n"
        "  \\pic at (0,0) {floorplan scale bar};\n"
        "  \\pic at (3,1) {floorplan north arrow};\n"
        "\\end{tikzpicture}\n"
    )
    pdf = _compile(tmp_path, compose("floorplan", "Weft", body, _OWNED))
    text = _text(pdf)
    assert text.count("1 m") == 1
    assert "N" in text


def _word_x(pdf, word):
    completed = subprocess.run(
        ["pdftotext", "-bbox", str(pdf), "-"],
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 0
    html = completed.stdout.decode("utf-8", "replace")
    match = re.search(
        rf'<word xMin="([0-9.]+)"[^>]*>{re.escape(word)}</word>',
        html,
    )
    assert match, html
    return float(match.group(1))


@pytest.mark.skipif(
    _XELATEX is None or _PDFTOTEXT is None, reason="poppler or xelatex missing"
)
def test_pid_pos_moves_the_flow_marker(tmp_path):
    """pos= is local to the path, so the marker moves and chemfig still places."""
    body = (
        "\\begin{tikzpicture}[circuit pid ISO14617]\n"
        "  \\draw[show, id=NEAR, flow path, pos=0.2] (0,0) -- (8,0);\n"
        "  \\draw[show, id=FAR, flow path, pos=0.8] (0,-1) -- (8,-1);\n"
        "\\end{tikzpicture}\n"
        "\\chemfig{H-[:30]O-[:-30]H}\n"
    )
    pdf = _compile(tmp_path, compose("pidcircuit", "Weft", body, _OWNED))
    assert _word_x(pdf, "NEAR") < _word_x(pdf, "FAR")
    assert "H" in _text(pdf)


@pytest.mark.skipif(
    _XELATEX is None or _PDFTOTEXT is None or _PDFFONTS is None,
    reason="xelatex, pdftotext, or pdffonts is not installed",
)
def test_fenced_tikz_preamble_embeds_zh_tw(tmp_path):
    """The fence PDF is the image HTML and DOCX embed. Glyphs must be in it."""
    lua = (_ROOT / "colophon/share/lock-diagram.lua").read_text(encoding="utf-8")
    font = lua.index("\\usepackage{fontspec}")
    cjk = lua.index("\\usepackage{xeCJK}")
    noto = lua.index("\\setCJKmainfont{Noto Sans CJK TC}")
    preamble = lua.index("\\input{colophon-v1-preamble.tex}")
    assert font < cjk < noto < preamble
    diagram = (_ROOT / "vendor/diagram/diagram.lua").read_text(encoding="utf-8")
    assert "-cnf-line=openin_any=p" in diagram
    tex = (
        "\\documentclass{standalone}\n"
        "\\usepackage{tikz}\n"
        "\\usepackage{fontspec}\n"
        "\\usepackage{xeCJK}\n"
        "\\setCJKmainfont{Noto Sans CJK TC}\n"
        "\\input{colophon-v1-preamble.tex}\n"
        "\\begin{document}\n"
        "\\begin{circuitikz}\n"
        "  \\draw (0,0) to[R, l=幫浦] (3,0) to[R, l=馬達] (6,0);\n"
        "\\end{circuitikz}\n"
        "\\end{document}\n"
    )
    pdf = _compile(tmp_path, tex)
    text = _text(pdf)
    assert "幫浦" in text
    assert "馬達" in text
    fonts = subprocess.run(
        ["pdffonts", str(pdf)],
        check=False,
        capture_output=True,
    )
    assert fonts.returncode == 0
    listed = fonts.stdout.decode("utf-8", "replace")
    assert "Noto" in listed
    assert "CJK" in listed
