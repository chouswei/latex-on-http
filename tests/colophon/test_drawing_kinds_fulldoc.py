# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R59. Every sold drawing kind renders inside a fulldoc Figure.

R59-KINDS: fulldoc inputs endleaf-kinds.tex, the colophon-v1 kind packages
less the two unsold ones. R59-TEMPLATES: the six named playbook kinds are
owned templates. R59-FLOAT: a landscape canvas inside a figure is a
landscape float page with no forced break. R59-OVERHANG: a picture past the
line is a layout_overhang warning. R59-TYPE: bytefield bit numbers and plot
tick labels use the Endleaf sans.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.layout_warn import (
    LAYOUT_CODE,
    layout_line,
    layout_warnings,
    parse_layout,
)
from colophon.templates import ALLOWED_INPUTS, TEMPLATE_IDS, compose, example_body

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"
_SHARE = _ROOT / "colophon/share/tex/latex/colophon-v1"
_REVIEW = _ROOT / "tests/colophon/fixtures/review"
_TEXINPUTS = os.pathsep.join(
    (
        str(_SHARE),
        str(_ROOT / "colophon/share/tex/latex/endleaf-floorplan"),
        str(_ROOT / "colophon/share/tex/latex/sysml-tikz"),
        str(_ROOT / "vendor/pidcircuittikz"),
        "",
    )
)
_NAMED = ("tikzcd", "forest", "automata", "mindmap", "tikztiming", "bytefield")
_UNSOLD = {"tikz-3dplot", "tikz-feynman"}
_NEEDS_TEX = pytest.mark.skipif(
    shutil.which("xelatex") is None or shutil.which("pdfinfo") is None,
    reason="xelatex or pdfinfo is not installed",
)


def _strip_comments(text):
    return "\n".join(line.split("%", 1)[0] for line in text.splitlines())


def _packages(text):
    found = set()
    for group in re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}", _strip_comments(text)):
        found.update(name.strip() for name in group.split(",") if name.strip())
    return found


def _libraries(text):
    found = set()
    for group in re.findall(r"\\usetikzlibrary\{([^}]*)\}", _strip_comments(text)):
        found.update(name.strip() for name in group.split(",") if name.strip())
    return found


def test_kinds_file_is_colophon_v1_less_unsold_packages():
    kinds = (_SHARE / "endleaf-kinds.tex").read_text(encoding="utf-8")
    colophon = (_SHARE / "colophon-v1-preamble.tex").read_text(encoding="utf-8")
    want = _packages(colophon) - _UNSOLD
    # Font and page packages belong to the template, not the kind list.
    want -= {"fontspec", "xeCJK", "geometry", "graphicx", "xcolor", "amsmath", "amssymb"}
    have = _packages(kinds)
    assert want <= have, sorted(want - have)
    assert not (have & _UNSOLD)
    for name in ("tikz-cd", "forest", "tikz-timing", "bytefield", "chemfig", "mhchem"):
        assert name in have
    assert _libraries(colophon) - {"3d", "perspective"} <= _libraries(kinds) | {"3d", "perspective"}


def test_fulldoc_inputs_kinds_file_and_it_is_allowed():
    text = (_OWNED / "fulldoc" / "preamble.tex").read_text(encoding="utf-8")
    assert r"\input{endleaf-kinds.tex}" in text
    assert "endleaf-kinds.tex" in ALLOWED_INPUTS
    assert r"\usepackage{tikz-feynman}" not in text
    assert r"\usepackage{tikz-3dplot}" not in text


def test_named_kinds_are_owned_templates():
    circuits = (_OWNED / "circuits" / "preamble.tex").read_text(encoding="utf-8")
    for kind in _NAMED:
        assert kind in TEMPLATE_IDS
        preamble = (_OWNED / kind / "preamble.tex").read_text(encoding="utf-8")
        assert f"templateId {kind}." in preamble.splitlines()[0]
        # Same preamble as circuits below the header line.
        assert preamble.splitlines()[1:] == circuits.splitlines()[1:]
        assert example_body(kind, _OWNED).strip()


def _xelatex(tmp_path, tex):
    (tmp_path / "job.tex").write_text(tex, encoding="utf-8")
    env = os.environ.copy()
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    for _ in range(2):
        completed = subprocess.run(
            ["xelatex", "-no-shell-escape", "-interaction=nonstopmode",
             "-halt-on-error", "job.tex"],
            cwd=tmp_path, check=False, timeout=240, capture_output=True, env=env,
        )
        log = (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")
        assert completed.returncode == 0, log[-2000:]
    return tmp_path / "job.pdf", log


def _page_sizes(pdf):
    out = subprocess.run(
        ["pdfinfo", "-f", "1", "-l", "99", str(pdf)],
        check=True, capture_output=True, text=True,
    ).stdout
    sizes = []
    for line in out.splitlines():
        found = re.match(r"^Page\s+\d+\s+size:\s+([0-9.]+)\s+x\s+([0-9.]+)", line)
        if found:
            sizes.append((float(found.group(1)), float(found.group(2))))
    return sizes


def _page_text(pdf, page):
    return subprocess.run(
        ["pdftotext", "-raw", "-f", str(page), "-l", str(page), str(pdf), "-"],
        check=True, capture_output=True, text=True,
    ).stdout


def _figure(body, caption, label):
    return (
        "\\begin{figure}[htbp]\n\\centering\n" + body.strip() + "\n"
        f"\\caption{{{caption}}}\\label{{{label}}}\n\\end{{figure}}\n"
    )


@_NEEDS_TEX
@pytest.mark.parametrize("kind", ("tikzcd", "forest", "tikztiming", "bytefield"))
def test_fulldoc_renders_the_four_missing_kinds(tmp_path, kind):
    body = (
        "\\section{Body}\nSee Figure~\\ref{fig:k}.\n\n"
        + _figure(example_body(kind, _OWNED), f"The {kind} figure", "fig:k")
    )
    pdf, log = _xelatex(tmp_path, compose("fulldoc", "Weft", body, _OWNED))
    assert not re.search(r"Environment \S+ undefined", log)
    assert "??" not in _page_text(pdf, 1)
    assert f"The {kind} figure" in subprocess.run(
        ["pdftotext", "-raw", str(pdf), "-"], check=True, capture_output=True, text=True
    ).stdout


@_NEEDS_TEX
def test_wide_sysml_figure_is_a_landscape_float_page_without_a_break(tmp_path):
    wide = (_REVIEW / "wide-175.tex").read_text(encoding="utf-8")
    narrow = "\\begin{tikzpicture}\\draw (0,0) rectangle (3,1);\\end{tikzpicture}"
    body = (
        "\\section{Overview}\nBefore the figure. See Figures~\\ref{fig:wide} and~\\ref{fig:small}.\n\n"
        + _figure(wide, "Wide system", "fig:wide")
        + "\\section{Notes}\nAfter the figure, still on the first page.\n\n"
        + _figure(narrow, "Small box", "fig:small")
        + "Closing words.\n"
    )
    pdf, log = _xelatex(tmp_path, compose("fulldoc", "Weft", body, _OWNED))
    sizes = _page_sizes(pdf)
    assert sizes[0][0] < sizes[0][1], sizes
    first = _page_text(pdf, 1)
    assert "After the figure" in first
    assert "Closing words" in first
    landscape = [index for index, (w, h) in enumerate(sizes, 1) if w > h]
    assert len(landscape) == 1, sizes
    assert "Wide system" in _page_text(pdf, landscape[0])
    assert "Small box" not in _page_text(pdf, landscape[0])
    # Order is kept: the small figure does not jump ahead of the wide one.
    for page in range(1, landscape[0]):
        assert "Small box" not in _page_text(pdf, page)
    assert all(w < h for index, (w, h) in enumerate(sizes, 1) if index != landscape[0])
    assert "ENDLEAF_OVERHANG" not in log
    assert "Overfull \\hbox" not in log


def test_layout_warnings_from_wrapped_log_lines():
    log = (
        "ENDLEAF_WIDE_PICTURE width=400.0pt line=345.0pt\n"
        "junk\nENDLEAF_OVER\nHANG package=sysml-tikz width=360.0pt line=345.0\npt\n"
        "ENDLEAF_WIDE_PICTURE width=345.5pt line=345.0pt\n"
    )
    warnings = layout_warnings(log)
    assert [item["packages"] for item in warnings] == [["sysml-tikz"], ["tikz"]]
    assert all(item["code"] == LAYOUT_CODE for item in warnings)
    assert "19.3 mm past the text line" in warnings[1]["message"]
    assert "5.3 mm" in warnings[0]["message"]
    assert layout_warnings("") == []
    assert layout_line([]) is None
    line = layout_line(warnings)
    assert parse_layout(("noise\n" + line + "\n").encode()) == warnings
    assert parse_layout("ENDLEAF_LAYOUT {bad") == []
    assert parse_layout('ENDLEAF_LAYOUT [{"code":"other","packages":["x"],"message":"m"}]') == []


def test_layout_warnings_count_pictures():
    log = "ENDLEAF_WIDE_PICTURE width=400pt line=345pt\nENDLEAF_WIDE_PICTURE width=360pt line=345pt\n"
    (item,) = layout_warnings(log)
    assert item["message"].startswith("a 2 pictures run up to 19.3 mm")


def test_endleaf_type_reaches_bytefield_and_plots():
    text = (_SHARE / "endleaf-type.tex").read_text(encoding="utf-8")
    assert r"bitformatting={\scriptsize\sffamily}" in text
    assert "bitwidth=auto" in text
    assert r"\DeclareSymbolFont{endleafsans}" in text
    assert "every tick label" in text
    assert r"\sisetup{mode=text}" in text


@_NEEDS_TEX
def test_bytefield_bit_numbers_are_at_least_seven_points(tmp_path):
    tex = compose("bytefield", "Weft", example_body("bytefield", _OWNED), _OWNED)
    pdf, _log = _xelatex(tmp_path, tex)
    out = subprocess.run(
        ["pdftotext", "-bbox", str(pdf), "-"], check=True, capture_output=True, text=True
    ).stdout
    heights = [
        float(y2) - float(y1)
        for y1, y2, word in re.findall(
            r'yMin="([0-9.]+)" xMax="[0-9.]+" yMax="([0-9.]+)">(\d+)</word>', out
        )
        if word in {"0", "8", "16", "24", "31"}
    ]
    assert heights, out[:500]
    # pdftotext reports the font size in bp: 7 pt is 6.97 bp. The old
    # \tiny default was 5 pt (4.98 bp).
    assert min(heights) >= 6.9, heights


@_NEEDS_TEX
def test_plot_tick_labels_use_the_endleaf_sans(tmp_path):
    body = (
        "\\begin{tikzpicture}\\begin{axis}[width=6cm]"
        "\\addplot coordinates {(-2,1) (0,3) (2,2)};\\end{axis}\\end{tikzpicture}"
    )
    pdf, _log = _xelatex(tmp_path, compose("plots", "Weft", body, _OWNED))
    fonts = subprocess.run(["pdffonts", str(pdf)], check=True, capture_output=True, text=True).stdout
    assert re.search(r"(?i)heros", fonts), fonts
    assert not re.search(r"CMR10|LMRoman10", fonts), fonts


def test_job_record_carries_layout_warnings(config, switch_path, monitor, auth):
    import json

    from colophon.killswitch import KillSwitch
    from colophon.runner import Outcome, Supervisor
    from colophon.worker import create_app
    from tests.colophon.conftest import valid_body

    warning = {
        "code": LAYOUT_CODE,
        "packages": ["tikz"],
        "message": "a picture runs 19.3 mm past the text line; narrow or split the picture",
    }
    outcome = Outcome(
        kind="ok",
        body=b"%PDF-1.4",
        content_type="application/pdf",
        wall_sec=0.5,
        memory_peak=100,
        pids_peak=3,
        layout_warnings=(warning,),
    )

    class _Runner:
        def __call__(self, job, name, abort_event):
            return outcome

    app = create_app(config, KillSwitch(switch_path), monitor, Supervisor(_Runner(), 10))
    response = app.test_client().post("/v1/jobs", json=valid_body(), headers=auth)
    record = json.loads(response.headers["X-Endleaf-Job"])
    assert warning in record["warnings"]


@_NEEDS_TEX
def test_sandbox_reports_a_wide_plain_picture(tmp_path, monkeypatch):
    from tests.colophon.conftest import valid_body
    from tests.colophon.test_fulldoc import _bind_tex, _render

    _bind_tex(monkeypatch, tmp_path)
    body = (
        "\\section{Wide}\nText.\n\n\\begin{figure}[htbp]\\centering\n"
        "\\begin{tikzpicture}\\draw (0,0) rectangle (16,1);\\end{tikzpicture}\n"
        "\\caption{Too wide}\\label{fig:w}\\end{figure}\n"
    )
    code, _pdf, err = _render(
        valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=body),
        monkeypatch,
    )
    assert code == 0, err[-2000:]
    (item,) = parse_layout(err)
    assert item["packages"] == ["tikz"]
    assert "past the text line" in item["message"]
