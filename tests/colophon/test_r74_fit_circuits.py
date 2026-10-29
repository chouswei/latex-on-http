"""ENDLEAF-R74: circuits symbols and the plain-picture fit.

R74-SYMBOLS: the PID library, loaded after circuitikz, must not leave its own
spring, damper and crossing styles in place of circuitikz's.
R74-TEXT: circuitikz's built-in text (thermistor, varistor, ecapacitor plus,
chip pin numbers) is at least 7 pt.
R74-FIT: a plain picture a little wider than the portrait line and taller than
a landscape text block is scaled to the line on its portrait page (no blank
landscape page, no clipping); a picture that fits has no paragraph indent.
The first group is TeX-free text checks; the compile tests skip when xelatex
or pdfinfo is missing.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.templates import compose_with_body_line

_ROOT = Path(__file__).resolve().parents[2]
_SHARE = _ROOT / "colophon/share"
_OWNED = _SHARE / "templates/owned"
_TEX = _SHARE / "tex/latex/colophon-v1"
_PREAMBLE = _TEX / "colophon-v1-preamble.tex"
_KINDS = _TEX / "endleaf-kinds.tex"
_FIT = _TEX / "endleaf-fit.tex"
_LAYOUT = _TEX / "endleaf-layout.tex"


def _code(path):
    return "\n".join(line.split("%", 1)[0] for line in path.read_text(encoding="utf-8").splitlines())


# --- TeX-free ----------------------------------------------------------------

def test_circuitikz_styles_are_restored_after_the_pid_library():
    text = _PREAMBLE.read_text(encoding="utf-8")
    code = _code(_PREAMBLE)
    pid = code.index(r"\usetikzlibrary{circuits.pid.ISO14617}")
    assert pid < code.index(r"\def\elcircuitikz@restore") < code.rindex(r"\elcircuitikz@restore")
    for name in ("spring", "damper", "crossing"):
        assert rf"\pgfcirc@activate@bipole@simple{{l}}{{{name}}}" in code
    assert r"\pgfcirc@style@to@style{crossing}{xing}" in code
    assert "ENDLEAF-R74-SYMBOLS" in text


def test_fulldoc_loads_circuitikz_after_the_pid_library():
    code = _code(_KINDS)
    assert code.index("circuits.pid.ISO14617") < code.index(r"\usepackage{circuitikz}")


@pytest.mark.parametrize("path", (_PREAMBLE, _KINDS))
def test_circuitikz_text_is_at_least_seven_points(path):
    code = _code(path)
    for macro in ("tiny", "sixbm"):
        m = re.search(rf"\\long\\def\\pgf@circ@font@{macro}\{{\\fontsize\{{(\d+(?:\.\d+)?)\}}", code)
        assert m and float(m.group(1)) >= 7, macro
    assert code.index(r"\usepackage{circuitikz}") < code.index(r"\pgf@circ@font@tiny")


def test_plain_pictures_scale_before_they_turn_and_have_no_indent():
    fit = _code(_FIT)
    plainfit = fit[fit.index(r"\def\elfit@plainfit{") :]
    assert plainfit.index(r"\elfit@plainscale") < plainfit.index("ENDLEAF_AUTO_LANDSCAPE")
    scale = fit[fit.index(r"\def\elfit@plainscale{") : fit.index(r"\def\tikzpicture{")]
    assert r"\elfit@plainht>\elfit@landth" in scale and "ENDLEAF_PICSCALE" in scale
    assert r"7\p@" in scale
    for text in (fit, _code(_LAYOUT)):
        close = text[text.index(r"\def\elfit@closetizpicture{") :]
        close = close[: close.index("\n}\n")]
        assert r"\ifvmode\noindent\fi\box\elfit@plainbox" in close
        assert r"\leavevmode\box\elfit@plainbox" not in close
    layout = _code(_LAYOUT)
    turned = layout[layout.index(r"\def\ellay@turned{") :]
    assert r"\ifelfit@plainstay\else" in turned[: turned.index("\n}\n")]


def test_vendored_fit_is_the_endleaf_prototype_when_both_repos_are_side_by_side():
    proto = _ROOT.parent / "endleaf/prototypes/endleaf-fit/endleaf-fit.tex"
    if proto.exists():
        assert proto.read_bytes() == _FIT.read_bytes()


# --- TeX ---------------------------------------------------------------------

_tex = pytest.mark.skipif(
    shutil.which("xelatex") is None or shutil.which("pdfinfo") is None, reason="xelatex/pdfinfo not installed"
)
PORTRAIT = "595.28 x 841.89"


def _texinputs(tmp_path):
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    found = ""
    if shutil.which("kpsewhich"):
        found = subprocess.run(
            ["kpsewhich", "tikzlibrarycircuits.pid.ISO14617.code.tex"],
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != "TEXINPUTS"},
        ).stdout.strip()
    if not found:
        (stub / "tikzlibrarycircuits.pid.ISO14617.code.tex").write_text("")
    return f".:{stub}:{_SHARE / 'tex'}//:"


def _compile(tmp_path, name, body):
    tex, _ = compose_with_body_line("circuits", "InstruMeasure", body, root=_OWNED)
    d = tmp_path / name
    d.mkdir()
    (d / "job.tex").write_text(tex, encoding="utf-8")
    env = dict(os.environ, TEXINPUTS=_texinputs(tmp_path))
    subprocess.run(["xelatex", "-interaction=nonstopmode", "job.tex"], cwd=d, env=env, capture_output=True, timeout=240)
    log = (d / "job.log").read_text(encoding="utf-8", errors="replace")
    info = subprocess.run(["pdfinfo", "-f", "1", "-l", "99", str(d / "job.pdf")], capture_output=True, text=True).stdout
    pages = [line.split(":", 1)[1].split("pts")[0].strip() for line in info.splitlines() if re.match(r"Page\s+\d+ size", line)]
    return pages, log


def _picture(width_cm, height_cm):
    return (
        rf"\begin{{circuitikz}}\draw (0,0) rectangle ({width_cm}cm,{height_cm}cm);"
        r"\node[font={\fontsize{7.5}{9}\selectfont}] at (1,1) {label};\end{circuitikz}"
    )


@_tex
def test_wide_and_tall_picture_is_scaled_on_one_portrait_page(tmp_path):
    pages, log = _compile(tmp_path, "tall", _picture(12.6, 14))
    assert pages == [PORTRAIT]
    assert "ENDLEAF_PICSCALE" in log and "ENDLEAF_AUTO_LANDSCAPE" not in log
    assert "ENDLEAF_PICTURN" not in log


@_tex
def test_picture_that_fits_has_no_false_overfull(tmp_path):
    pages, log = _compile(tmp_path, "fits", _picture(12.0, 6))
    assert pages == [PORTRAIT] and "Overfull" not in log


@_tex
def test_spring_damper_crossing_draw_after_the_pid_library(tmp_path):
    body = (
        r"\begin{circuitikz}\draw (0,0) to[spring] (2,0); \draw (0,-1) to[damper] (2,-1);"
        r"\draw (0,-2) to[crossing] (2,-2); \draw (0,-3) to[xing] (2,-3);\end{circuitikz}"
    )
    pages, log = _compile(tmp_path, "symbols", body)
    assert pages == [PORTRAIT] and "Undefined control sequence" not in log
