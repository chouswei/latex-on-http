"""ENDLEAF-R70-FIGOPT: a figure with no [..] option takes the class default.

endleaf-fit.tex redefines \\figure. Without an option it must expand
\\fps@figure before \\@xfloat reads the list token by token, or LaTeX
stops with "Unknown float option `\\'". Pandoc's Figure (a document-shell
fence with caption=) always opens \\begin{figure} with no option.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.layout_warn import LAYOUT_CODE, SCALED_CODE, final_pass, layout_warnings
from colophon.templates import compose_with_body_line

_ROOT = Path(__file__).resolve().parents[2]
_SHARE = _ROOT / "colophon/share"
_OWNED = _SHARE / "templates/owned"
_FIT = _SHARE / "tex/latex/colophon-v1/endleaf-fit.tex"
_DIAGRAM = _ROOT / "vendor/diagram/diagram.lua"
FIT_KINDS = tuple(
    sorted(p.parent.name for p in _OWNED.glob("*/preamble.tex") if "endleaf-fit.tex" in p.read_text(encoding="utf-8"))
)
PORTRAIT = "595.28 x 841.89"
LANDSCAPE = "841.89 x 595.28"


def test_fit_kinds_cover_drawing_sysml_fulldoc():
    assert {"circuits", "plots", "sysml", "fulldoc"} <= set(FIT_KINDS) and len(FIT_KINDS) == 14


def test_default_placement_is_expanded():
    fit = _FIT.read_text(encoding="utf-8")
    assert (
        "\\def\\figure{\\@ifnextchar[\\elfit@figopt{\\expandafter\\elfit@figopt\\expandafter[\\fps@figure]}}" in fit
    )
    assert "{\\elfit@figopt[\\fps@figure]}" not in fit


def _texinputs(tmp_path):
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "TEXINPUTS"}
    found = subprocess.run(
        ["kpsewhich", "tikzlibrarycircuits.pid.ISO14617.code.tex"], capture_output=True, text=True, env=env
    ).stdout.strip()
    if not found:
        (stub / "tikzlibrarycircuits.pid.ISO14617.code.tex").write_text("")
    return f".:{stub}:{_SHARE / 'tex'}//:"


def _pages(pdf):
    info = subprocess.run(["pdfinfo", "-f", "1", "-l", "99", str(pdf)], capture_output=True, text=True).stdout
    return [l.split(":", 1)[1].split("pts")[0].strip() for l in info.splitlines() if re.match(r"Page\s+\d+ size", l)]


_tex = pytest.mark.skipif(
    shutil.which("xelatex") is None or shutil.which("pdfinfo") is None, reason="xelatex/pdfinfo not installed"
)
_NO_OPT = (
    "Intro.\n\n\\begin{figure}\n\\centering\n\\begin{tikzpicture}\\draw (0,0) rectangle (4,2);"
    "\\node at (2,1) {box};\\end{tikzpicture}\n\\caption{No option}\n\\end{figure}\n\nAfter.\n"
)


@_tex
@pytest.mark.parametrize("kind", FIT_KINDS)
def test_figure_without_option_compiles(tmp_path, kind):
    tex, _ = compose_with_body_line(kind, "InstruMeasure", _NO_OPT, root=_OWNED)
    (tmp_path / "job.tex").write_text(tex, encoding="utf-8")
    env = dict(os.environ, TEXINPUTS=_texinputs(tmp_path))
    subprocess.run(
        ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "job.tex"],
        cwd=tmp_path, env=env, capture_output=True, timeout=240,
    )
    log = (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")
    assert "Unknown float option" not in log
    assert (tmp_path / "job.pdf").exists(), log[-2000:]


def _pandoc3():
    if shutil.which("pandoc") is None or shutil.which("xelatex") is None or not _DIAGRAM.exists():
        return False
    out = subprocess.run(["pandoc", "--version"], capture_output=True, text=True).stdout
    m = re.match(r"pandoc (\d+)", out)
    return bool(m and int(m.group(1)) >= 3)


_pandoc = pytest.mark.skipif(not _pandoc3(), reason="pandoc 3 / xelatex not installed")


def _fence(tmp_path, width_cm):
    """The live document-shell path: lock-diagram.lua, then pandoc-ext/diagram,
    a tikz fence with caption= (a Pandoc Figure), the lane template."""
    lock = (_SHARE / "lock-diagram.lua").read_text(encoding="utf-8")
    # The image's non-escape wrapper is not on a dev box; plain xelatex.
    (tmp_path / "lock.lua").write_text(lock.replace("/usr/local/bin/xelatex-nonescape", "xelatex"), encoding="utf-8")
    md = tmp_path / f"s{width_cm}.md"
    md.write_text(
        "# Wide picture\n\nSome text before.\n\n"
        f'```{{.tikz caption="A {width_cm} cm figure" alt="A wide box"}}\n'
        f"\\begin{{tikzpicture}}\n\\draw[thick] (0,0) rectangle ({width_cm},4);\n"
        f"\\node at ({width_cm / 2},2) {{{width_cm} cm wide}};\n\\end{{tikzpicture}}\n```\n\nText after.\n",
        encoding="utf-8",
    )
    pdf = tmp_path / f"s{width_cm}.pdf"
    cmd = [
        "pandoc", str(md), "--from", "markdown", "--lua-filter", str(tmp_path / "lock.lua"),
        "--lua-filter", str(_DIAGRAM), "--verbose", "--pdf-engine", "xelatex",
        "--template", str(_SHARE / "templates/InstruMeasure/pandoc.latex"),
        "-V", "papersize=a4", "-V", "endleafpaper=A4", "-o", str(pdf),
    ]
    env = dict(os.environ, TEXINPUTS=_texinputs(tmp_path))
    done = subprocess.run(cmd, cwd=tmp_path, capture_output=True, env=env, timeout=300)
    out = done.stdout + done.stderr
    assert b"Unknown float option" not in out
    assert done.returncode == 0, out[-2000:]
    return _pages(pdf), layout_warnings(final_pass(out)), pdf


@_pandoc
def test_verify_fence_13cm_shrinks_on_portrait(tmp_path):
    pages, (item,), _ = _fence(tmp_path, 13)
    assert pages == [PORTRAIT] and item["code"] == SCALED_CODE and item["minTextPt"] >= 7


@_pandoc
def test_verify_fence_22cm_turns_landscape_centred(tmp_path):
    pages, (item,), pdf = _fence(tmp_path, 22)
    assert pages[-1] == LANDSCAPE and item["landscape"] is True and item["code"] == SCALED_CODE
    assert item["minTextPt"] >= 7
    n = len(pages)
    box = subprocess.run(["pdftotext", "-bbox", "-f", str(n), "-l", str(n), str(pdf), "-"], capture_output=True, text=True).stdout
    x0 = float(re.search(r'xMin="([0-9.]+)"[^>]*>22<', box).group(1))
    x1 = float(re.search(r'xMax="([0-9.]+)"[^>]*>wide<', box).group(1))
    assert abs((x0 + x1) / 2 - 841.89 / 2) < 2


@_pandoc
def test_verify_fence_40cm_floor_scale_warns(tmp_path):
    pages, (item,), _ = _fence(tmp_path, 40)
    assert pages[-1] == LANDSCAPE and item["code"] == LAYOUT_CODE and item["belowTypeFloor"] is True
