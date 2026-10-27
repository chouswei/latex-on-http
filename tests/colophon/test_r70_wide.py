"""ENDLEAF-R70: wide pictures outside fulldoc.

R70-KINDS: every TeX drawing kind except stocklabel inputs endleaf-fit.tex
(and endleaf-layout.tex for its page and fit lines); a bare picture that
turns its own page is centred on the landscape line.
R70-SHELL: a document-shell diagram fence shrinks only while its type stays
at or above 7 pt, else turns landscape (no job orientation), else stops at
the floor scale; each fence logs a line the worker turns into a warning.
R70-KEEP: sysml and fulldoc preambles are unchanged.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.layout_warn import (
    LAYOUT_CODE,
    SCALED_CODE,
    final_pass,
    layout_line,
    layout_warnings,
    parse_layout,
)
from colophon.templates import compose_with_body_line

_ROOT = Path(__file__).resolve().parents[2]
_SHARE = _ROOT / "colophon/share"
_OWNED = _SHARE / "templates/owned"
_FIT = _SHARE / "tex/latex/colophon-v1/endleaf-fit.tex"
DRAWING_KINDS = (
    "pidcircuit", "circuits", "plots", "chemistry", "gantt", "floorplan",
    "tikzcd", "forest", "automata", "mindmap", "tikztiming", "bytefield",
)
LANES = ("InstruMeasure", "Investor", "Weft")


@pytest.mark.parametrize("kind", DRAWING_KINDS)
def test_drawing_kind_inputs_fit_then_layout_with_bare_centre(kind):
    pre = (_OWNED / kind / "preamble.tex").read_text(encoding="utf-8")
    flag = pre.index(r"\def\EndleafBareCentre{}")
    fit = pre.index(r"\input{endleaf-fit.tex}")
    layout = pre.index(r"\input{endleaf-layout.tex}")
    assert pre.index(r"\input{colophon-v1-preamble.tex}") < flag < fit < layout < pre.index(r"\begin{document}")


@pytest.mark.parametrize("kind", ("stocklabel", "sysml", "fulldoc", "document-shell"))
def test_other_templates_do_not_set_bare_centre(kind):
    assert "EndleafBareCentre" not in (_OWNED / kind / "preamble.tex").read_text(encoding="utf-8")


def test_stocklabel_does_not_input_fit():
    assert "endleaf-fit.tex" not in (_OWNED / "stocklabel/preamble.tex").read_text(encoding="utf-8")


def test_bare_centre_is_gated_by_the_flag():
    fit = _FIT.read_text(encoding="utf-8")
    assert "\\ifdefined\\EndleafBareCentre\n  \\def\\elfit@barecentre{" in fit
    assert "\\else\n  \\let\\elfit@barecentre\\relax\n\\fi" in fit
    centre = fit[fit.index(r"\def\elfit@plaincentre{") :]
    centre = centre[: centre.index("\n}\n")]
    assert r"\else" in centre and r"\elfit@barecentre" in centre


@pytest.mark.parametrize("lane", LANES)
def test_lane_points_pandocbounded_at_fence_fit(lane):
    text = (_SHARE / "templates" / lane / "pandoc.latex").read_text(encoding="utf-8")
    assert text.index(r"\input{colophon-v1-preamble.tex}") < text.index(r"\input{endleaf-fit.tex}")
    assert r"\renewcommand*\pandocbounded[1]{\elfit@bounded{#1}}" in text


def test_markdown_pdf_plan_is_verbose():
    from colophon.enums import JobSpec
    from colophon.render_plan import build_render_plan

    job = JobSpec(source="# T\n", input_kind="markdown", output_format="pdf", lane="InstruMeasure")
    (command,) = build_render_plan(job).commands
    assert "--verbose" in command
    html = JobSpec(source="# T\n", input_kind="markdown", output_format="html", lane="InstruMeasure")
    (command,) = build_render_plan(html).commands
    assert "--verbose" not in command


# --- worker parsing (TeX-free) ---------------------------------------------

def _shell(n, natural, line, scale, page, orient, turned=False):
    return (
        f"ENDLEAF_SHELLFIT {n} {natural}pt {line}pt 10 {scale}\n"
        + (f"ENDLEAF_SHELLTURN {n}\n" if turned else "")
        + f"[{page} ENDLEAF_SHELLPAGE {n} {page} {orient}]\n"
    )


def test_shell_13cm_is_a_typed_shrink_note_on_portrait():
    (item,) = layout_warnings(_shell(1, "370.28247", "345.0", "0.93172", 1, "portrait"))
    assert item["code"] == SCALED_CODE and item["scale"] == 0.93 and item["minTextPt"] == 9.3
    assert item["page"] == 1 and "landscape" not in item
    assert item["message"] == "pg1: a diagram was shrunk to 0.93; its text is 9.3 pt"


def test_shell_22cm_turns_and_shrinks():
    (item,) = layout_warnings(_shell(1, "626.3585", "592.53897", "0.94608", 1, "landscape", True))
    assert item["code"] == SCALED_CODE and item["landscape"] is True and item["minTextPt"] == 9.4


def test_shell_40cm_stops_at_floor_and_overhangs():
    (item,) = layout_warnings(_shell(1, "1138.51067", "592.53897", "0.7", 1, "landscape", True))
    assert item["code"] == LAYOUT_CODE and item["landscape"] is True and item["page"] == 1
    assert item["belowTypeFloor"] is True and item["scaleToFit"] == 0.52
    assert item["fix"] == "already landscape; redraw or split; scaling would put text at 5.2 pt"
    assert ". Fix: already landscape;" in item["message"]


def test_shell_named_portrait_stops_at_floor_without_turning():
    (item,) = layout_warnings(_shell(1, "626.3585", "345.0", "0.7", 1, "portrait"))
    assert item["code"] == LAYOUT_CODE and "landscape" not in item
    assert item["fix"].startswith("redraw or split")


def test_unscaled_fence_is_silent_and_items_survive_the_wire():
    assert layout_warnings(_shell(1, "200.0", "345.0", "1", 1, "portrait")) == []
    items = layout_warnings(_shell(1, "370.28247", "345.0", "0.93172", 1, "portrait"))
    assert parse_layout(layout_line(items)) == items


def test_final_pass_reads_only_the_last_latex_run():
    out = (
        "[INFO] [makePDF] Source:\nENDLEAF_SHELLFIT 9 999pt 1pt 10 0.1\n"
        "[INFO] [makePDF] LaTeX run number 1\n" + _shell(1, "400", "345.0", "0.8625", 1, "portrait")
        + "[INFO] [makePDF] LaTeX run number 2\n" + _shell(1, "370.28247", "345.0", "0.93172", 1, "portrait")
    )
    (item,) = layout_warnings(final_pass(out.encode()))
    assert item["scale"] == 0.93


# --- TeX ------------------------------------------------------------------

def _texinputs(tmp_path):
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    found = subprocess.run(
        ["kpsewhich", "tikzlibrarycircuits.pid.ISO14617.code.tex"],
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "TEXINPUTS"},
    ).stdout.strip()
    if not found:
        # The image carries the PID library; a dev box may not.
        (stub / "tikzlibrarycircuits.pid.ISO14617.code.tex").write_text("")
    return f".:{stub}:{_SHARE / 'tex'}//:"


def _pages(pdf):
    info = subprocess.run(["pdfinfo", "-f", "1", "-l", "99", str(pdf)], capture_output=True, text=True).stdout
    return [line.split(":", 1)[1].split("pts")[0].strip() for line in info.splitlines() if re.match(r"Page\s+\d+ size", line)]


PORTRAIT = "595.28 x 841.89"
LANDSCAPE = "841.89 x 595.28"
_BODIES = {
    "circuits": r"\begin{circuitikz}\draw (0,0) to[R=$R_1$] (Wcm,0) to[C] (Wcm,2) -- (0,2) -- (0,0);"
    r"\node at (Wcm/2,1) {wide circuit};\end{circuitikz}",
    "plots": r"\begin{tikzpicture}\begin{axis}[width=Vcm,height=5cm,scale only axis]"
    r"\addplot{x^2};\end{axis}\end{tikzpicture}",
}


def _kind(tmp_path, kind, width_cm, orientation=None):
    body = _BODIES[kind].replace("Wcm", f"{width_cm}cm").replace("Vcm", f"{width_cm - 1}cm")
    tex, _ = compose_with_body_line(kind, "InstruMeasure", body, root=_OWNED, orientation=orientation)
    d = tmp_path / f"{kind}-{width_cm}-{orientation}"
    d.mkdir()
    (d / "job.tex").write_text(tex, encoding="utf-8")
    env = dict(os.environ, TEXINPUTS=_texinputs(tmp_path))
    subprocess.run(["xelatex", "-interaction=nonstopmode", "job.tex"], cwd=d, env=env, capture_output=True, timeout=240)
    log = (d / "job.log").read_text(encoding="utf-8", errors="replace")
    return _pages(d / "job.pdf"), log, d / "job.pdf"


_tex = pytest.mark.skipif(
    shutil.which("xelatex") is None or shutil.which("pdfinfo") is None, reason="xelatex/pdfinfo not installed"
)


@_tex
@pytest.mark.parametrize("kind", ("circuits", "plots"))
def test_kind_10cm_stays_portrait(tmp_path, kind):
    pages, log, _ = _kind(tmp_path, kind, 10)
    assert pages == [PORTRAIT] and layout_warnings(log) == []


@_tex
@pytest.mark.parametrize("kind", ("circuits", "plots"))
def test_kind_15cm_turns_landscape_and_fits(tmp_path, kind):
    pages, log, _ = _kind(tmp_path, kind, 15)
    assert pages == [LANDSCAPE] and layout_warnings(log) == []
    assert "Overfull \\hbox" not in log


@_tex
@pytest.mark.parametrize("kind", ("circuits", "plots"))
def test_kind_22cm_turns_and_warns_with_page(tmp_path, kind):
    pages, log, _ = _kind(tmp_path, kind, 22)
    assert pages == [LANDSCAPE]
    items = layout_warnings(log)
    assert items and all(i["page"] == 1 and i["landscape"] is True for i in items)
    assert all(i["fix"].startswith("already landscape;") for i in items)


@_tex
def test_circuit_22cm_is_centred_on_the_landscape_page(tmp_path):
    _, _, pdf = _kind(tmp_path, "circuits", 22)
    box = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"], capture_output=True, text=True).stdout
    x0 = float(re.search(r'xMin="([0-9.]+)"[^>]*>wide<', box).group(1))
    x1 = float(re.search(r'xMax="([0-9.]+)"[^>]*>circuit<', box).group(1))
    # The label sits at the picture's middle; the page middle is 420.9 pt.
    assert abs((x0 + x1) / 2 - 841.89 / 2) < 12


@_tex
@pytest.mark.parametrize("kind", ("circuits", "plots"))
def test_kind_named_portrait_never_turns(tmp_path, kind):
    pages, log, _ = _kind(tmp_path, kind, 22, orientation="portrait")
    assert pages == [PORTRAIT]
    items = layout_warnings(log)
    assert items and all("landscape" not in i for i in items)
    assert "ENDLEAF_PICTURN" not in log


def _shell_render(tmp_path, width_cm, orientation=None):
    img = tmp_path / f"img{width_cm}.tex"
    img.write_text(
        "\\documentclass[border=0pt]{standalone}\\usepackage{tikz}\\begin{document}\\begin{tikzpicture}"
        f"\\draw (0,0) rectangle ({width_cm}cm,3cm); \\node at ({width_cm / 2}cm,1.5cm) {{Fence}};"
        "\\end{tikzpicture}\\end{document}\n"
    )
    subprocess.run(["xelatex", "-interaction=nonstopmode", img.name], cwd=tmp_path, capture_output=True, timeout=120)
    md = tmp_path / f"s{width_cm}.md"
    md.write_text(f"Intro.\n\n![]({tmp_path / f'img{width_cm}.pdf'})\n\nAfter.\n")
    cmd = [
        "pandoc", str(md), "--verbose", "--pdf-engine", "xelatex",
        "--template", str(_SHARE / "templates/InstruMeasure/pandoc.latex"),
        "-V", "papersize=a4", "-V", "endleafpaper=A4",
        *(("-V", f"endleaforientation={orientation}") if orientation else ()),
        "-o", str(tmp_path / f"s{width_cm}.pdf"),
    ]
    env = dict(os.environ, TEXINPUTS=_texinputs(tmp_path))
    done = subprocess.run(cmd, capture_output=True, env=env, timeout=300)
    assert done.returncode == 0, done.stdout[-2000:]
    return _pages(tmp_path / f"s{width_cm}.pdf"), layout_warnings(final_pass(done.stdout + done.stderr))


_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None or shutil.which("xelatex") is None, reason="pandoc not installed")


@_pandoc
def test_shell_fence_13cm_shrinks_on_portrait(tmp_path):
    pages, (item,) = _shell_render(tmp_path, 13)
    assert pages == [PORTRAIT] and item["code"] == SCALED_CODE and item["minTextPt"] >= 7


@_pandoc
def test_shell_fence_22cm_turns_landscape(tmp_path):
    pages, (item,) = _shell_render(tmp_path, 22)
    assert pages == [LANDSCAPE] and item["landscape"] is True and item["code"] == SCALED_CODE


@_pandoc
def test_shell_fence_40cm_floor_scale_warns(tmp_path):
    pages, (item,) = _shell_render(tmp_path, 40)
    assert pages == [LANDSCAPE] and item["code"] == LAYOUT_CODE and item["belowTypeFloor"] is True


@_pandoc
def test_shell_fence_named_portrait_stops_at_floor(tmp_path):
    pages, (item,) = _shell_render(tmp_path, 22, orientation="portrait")
    assert pages == [PORTRAIT] and item["code"] == LAYOUT_CODE and "landscape" not in item
