"""ENDLEAF-R69-AUTO in fulldoc: endleaf-layout.tex must not bypass \\elfit@plainfit (TeX-free text checks)."""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TEX = _ROOT / "colophon/share/tex/latex/colophon-v1"
_PREAMBLE = _ROOT / "colophon/share/templates/owned/fulldoc/preamble.tex"


def _close_def(text):
    start = text.index(r"\def\elfit@closetizpicture{")
    depth = 0
    for i in range(text.index("{", start), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError("unbalanced \\elfit@closetizpicture")


def _code(text):
    return "\n".join(line.split("%", 1)[0] for line in text.splitlines())


def test_layout_close_calls_plainfit_outside_a_canvas():
    body = _code(_close_def((_TEX / "endleaf-layout.tex").read_text()))
    outside = body.split(r"\else", 1)[1]
    assert r"\elfit@plainfit" in outside
    # PICFIT reports the line the picture is set on (landscape line after a turn), not \linewidth.
    assert r"\ellay@fit{plain}\elfit@plainbox\elfit@plainline" in outside
    assert outside.index(r"\elfit@plainfit") < outside.index(r"\ellay@fit{plain}")
    # plainfit already logs ENDLEAF_WIDE_PICTURE outside a canvas; no second line there.
    assert "ENDLEAF_WIDE_PICTURE" not in outside
    assert r"\leavevmode\box\elfit@plainbox" in body


def test_layout_inside_a_canvas_does_not_turn_the_page():
    body = _code(_close_def((_TEX / "endleaf-layout.tex").read_text()))
    inside = body.split(r"\ifellay@incanvas", 1)[1].split(r"\else", 1)[0]
    assert r"\elfit@plainfit" not in inside and "ENDLEAF_WIDE_PICTURE" in inside


def test_plainfit_is_defined_by_fit_before_layout_is_input():
    fit = _code((_TEX / "endleaf-fit.tex").read_text())
    assert re.search(r"\\def\\elfit@plainfit\{", fit) and r"\newdimen\elfit@plainline" in fit
    pre = _PREAMBLE.read_text()
    assert pre.index(r"\input{endleaf-fit.tex}") < pre.index(r"\input{endleaf-layout.tex}")
