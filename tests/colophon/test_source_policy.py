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
        ("\\immediate\\write18{echo no}", "write18"),
        ("\\write 18 {echo no}", "write18"),
        ("\\ShellEscape", "shell-escape"),
        ("\\usepackage{minted}", "minted"),
        ("\\begin{minted}{python}\n", "minted"),
        ("\\usetikzlibrary{calc,external}", "tikz-external"),
        ("\\tikzexternalize", "tikz-external"),
        ("\\usepackage{asymptote}", "asymptote"),
        ("\\begin{asy}\ndraw((0,0)--(1,1));\n\\end{asy}", "asymptote"),
        ("```asymptote\ndraw((0,0)--(1,0));\n```", "asymptote"),
        ("\\usepackage{gnuplottex}", "gnuplot"),
        ("\\begin{gnuplot}\nplot x\n\\end{gnuplot}", "gnuplot"),
        ("\\usepackage{epstopdf}", "epstopdf"),
        ("\\epstopdfsetup{update}", "epstopdf"),
        ("\\usepackage{svg}", "svg"),
        ("\\includesvg{figure}", "svg"),
        ("\\feynmandiagram [horizontal=a to b] { a -- b, };", "feynman-auto"),
        ("\\diagram {(a) -- (b)};", "feynman-auto"),
    ],
)
def test_forbidden_source_is_refused_before_compile(source, reason):
    with pytest.raises(JobRejected) as caught:
        parse_job(_job(source, input_kind="markdown"))
    assert caught.value.reason == reason


def test_negative_fixtures_are_refused():
    expected = {
        "reject-shell-escape.tex": "write18",
        "reject-minted.tex": "minted",
        "reject-tikz-external.tex": "tikz-external",
        "reject-asymptote.tex": "asymptote",
        "reject-gnuplot.tex": "gnuplot",
        "reject-epstopdf.tex": "epstopdf",
        "reject-svg.tex": "svg",
        "reject-feynman-auto.tex": "feynman-auto",
    }
    for name, reason in expected.items():
        text = (FIXTURES / name).read_text(encoding="utf-8")
        with pytest.raises(JobRejected) as caught:
            reject_forbidden_source(text)
        assert caught.value.reason == reason


def test_prose_about_shell_escape_is_allowed():
    parse_job(
        _job("do not enable shell-escape in this note.", input_kind="markdown")
    )
    parse_job(_job("Use -no-shell-escape only.", input_kind="markdown"))


def test_manual_feynman_layout_is_allowed():
    source = "\\vertex (a);\n\\diagram* {(a) -- (b)};"
    reject_forbidden_source(source)
    parse_job(_job(source, input_kind="markdown"))


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
    assert "Shoelace helper" in text or "\\floorplanPolygonArea" in text
    assert "\\floorplanPolygonArea" in text
    assert "scale/1000" in text


def test_compile_fixtures_exist_for_the_image_build():
    """Direct XeLaTeX for these files is an install check, not the wrapper path."""
    for name in ("packages-once.tex", "floorplan-two-room.tex"):
        text = (FIXTURES / name).read_text(encoding="utf-8")
        assert "\\documentclass" in text
        reject_forbidden_source(text)
    assert "floorplan room label={Room A}{(0,0)}{(4,3)}" in (
        FIXTURES / "floorplan-two-room.tex"
    ).read_text(encoding="utf-8")


def test_kind_fixtures_cover_each_engine_package():
    kinds = FIXTURES / "kinds"
    packages = (
        "circuitikz",
        "siunitx",
        "pgfplots",
        "chemfig",
        "mhchem",
        "tikz-3dplot",
        "tikz-feynman",
        "tikz-cd",
        "forest",
        "tikz-timing",
        "bytefield",
        "pgfgantt",
        "tikz-dimline",
        "tikzscale",
        "colophon-floorplan",
    )
    for name in packages:
        tex = (kinds / f"{name}.tex").read_text(encoding="utf-8")
        markdown = (kinds / f"{name}.md").read_text(encoding="utf-8")
        assert "\\documentclass" not in tex
        assert "```tikz" in markdown
        reject_forbidden_source(tex)
        reject_forbidden_source(markdown)
    half = (kinds / "colophon-floorplan-scale.tex").read_text(encoding="utf-8")
    assert "scale=0.5" in half
    assert "\\documentclass" not in half
    reject_forbidden_source(half)
    for extra in ("mermaid.md", "d2.md", "pid.tex", "tikz-libraries.tex"):
        reject_forbidden_source((kinds / extra).read_text(encoding="utf-8"))


def test_shared_preamble_is_the_only_package_list():
    root = Path(__file__).resolve().parents[2]
    preamble = (
        root / "colophon/share/tex/latex/colophon-v1/colophon-v1-preamble.tex"
    ).read_text(encoding="utf-8")
    for name in (
        "circuitikz",
        "siunitx",
        "pgfplots",
        "chemfig",
        "mhchem",
        "tikz-3dplot",
        "tikz-feynman",
        "tikz-cd",
        "forest",
        "tikz-timing",
        "bytefield",
        "pgfgantt",
        "tikz-dimline",
        "tikzscale",
        "colophon-floorplan",
        "circuits.pid.ISO14617",
    ):
        assert name in preamble
    for lane in ("Weft", "InstruMeasure", "Investor"):
        wrapper = (
            root / f"colophon/share/templates/{lane}/wrapper.tex"
        ).read_text(encoding="utf-8")
        template = (
            root / f"colophon/share/templates/{lane}/pandoc.latex"
        ).read_text(encoding="utf-8")
        assert "\\input{colophon-v1-preamble.tex}" in wrapper
        assert "\\input{colophon-v1-preamble.tex}" in template
        assert "\\usepackage{circuitikz}" not in wrapper
        assert "\\usepackage{circuitikz}" not in template
    lock = (root / "colophon/share/lock-diagram.lua").read_text(encoding="utf-8")
    assert "\\input{colophon-v1-preamble.tex}" in lock
    diagram = (root / "vendor/diagram/diagram.lua").read_text(encoding="utf-8")
    assert "dgr_opt.opt[optname] = value" in diagram
    assert "dgr_opt.opt[optname] or value" not in diagram
