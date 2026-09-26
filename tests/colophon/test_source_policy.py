# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

import pytest

from colophon.enums import JobRejected, parse_job
from colophon.source_policy import reject_forbidden_source

FIXTURES = Path(__file__).parent / "fixtures"
STYLES = (
    "floorplan wall",
    "floorplan door",
    "floorplan window",
    "floorplan room label",
    "floorplan scale bar",
    "floorplan north arrow",
    "floorplan dimension",
)


def _job(source, input_kind="tex"):
    return {
        "input": source,
        "inputKind": input_kind,
        "outputFormat": "pdf",
        "lane": "Weft",
    }


@pytest.mark.parametrize(
    "source,reason",
    [
        ("See -shell-escape please", "shell-escape"),
        ("\\immediate\\write18{echo no}", "write18"),
        ("\\write 18 {echo no}", "write18"),
        ("\\usepackage{minted}", "minted"),
        ("\\begin{minted}{python}\n", "minted"),
        ("\\usetikzlibrary{calc,external}", "tikz-external"),
        ("\\tikzexternalize", "tikz-external"),
        ("\\usepackage{asymptote}", "asymptote"),
        ("\\begin{asy}\ndraw((0,0)--(1,1));\n\\end{asy}", "asymptote"),
        ("```asymptote\ndraw((0,0)--(1,0));\n```", "asymptote"),
    ],
)
def test_forbidden_source_is_refused_before_compile(source, reason):
    with pytest.raises(JobRejected) as caught:
        parse_job(_job(source, input_kind="markdown"))
    assert caught.value.reason == reason


def test_negative_fixtures_are_refused():
    shell = (FIXTURES / "reject-shell-escape.tex").read_text(encoding="utf-8")
    asy = (FIXTURES / "reject-asymptote.tex").read_text(encoding="utf-8")
    with pytest.raises(JobRejected) as shell_caught:
        reject_forbidden_source(shell)
    assert shell_caught.value.reason == "write18"
    with pytest.raises(JobRejected) as asy_caught:
        reject_forbidden_source(asy)
    assert asy_caught.value.reason == "asymptote"


def test_no_shell_escape_flag_is_not_a_request():
    parse_job(_job("Use -no-shell-escape only.", input_kind="markdown"))


def test_floorplan_styles_are_defined():
    text = (
        Path(__file__).resolve().parents[2]
        / "colophon"
        / "share"
        / "tex"
        / "latex"
        / "colophon-floorplan"
        / "colophon-floorplan.sty"
    ).read_text(encoding="utf-8")
    for name in STYLES:
        assert f"{name}/." in text
    assert "plan-scale" in text
    assert "tikz-dimline" in text
    assert "siunitx" in text


def test_compile_fixtures_exist_for_the_image_build():
    """XeLaTeX for these files runs in the image build, not in unit CI."""
    for name in ("packages-once.tex", "floorplan-two-room.tex"):
        text = (FIXTURES / name).read_text(encoding="utf-8")
        assert "\\documentclass" in text
        reject_forbidden_source(text)
