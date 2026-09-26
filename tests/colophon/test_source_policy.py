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
    template = "document-shell" if input_kind == "markdown" else "circuits"
    return {
        "body": source,
        "templateId": template,
        "outputFormat": "pdf",
        "lane": "Weft",
    }


@pytest.mark.parametrize(
    "source,reason",
    [
        ("\\immediate\\write18{echo no}", "write18"),
        ("\\write 18 {echo no}", "write18"),
        ("\\ShellEscape", "shell-escape"),
        ("\\directlua{os.execute([[echo]])}", "directlua"),
        ("\\usepackage{minted}", "minted"),
        ("\\begin{minted}{python}\n", "minted"),
        ("\\usetikzlibrary{calc,external}", "tikz-external"),
        ("\\tikzexternalize", "tikz-external"),
        ("\\usepackage{asymptote}", "asymptote"),
        ("\\begin{asy}\ndraw((0,0)--(1,1));\n\\end{asy}", "asymptote"),
        ("```asymptote\ndraw((0,0)--(1,0));\n```", "asymptote"),
        ("```mermaid\ngraph TD\n  A-->B\n```", "mermaid"),
        ("~~~{.mermaid}\ngraph TD\n  A-->B\n~~~", "mermaid"),
        ("```d2\nA -> B\n```", "d2"),
        ("``` {.d2}\nA -> B\n```", "d2"),
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
        "reject-mermaid.md": "mermaid",
        "reject-d2.md": "d2",
    }
    for name, reason in expected.items():
        text = (FIXTURES / name).read_text(encoding="utf-8")
        with pytest.raises(JobRejected) as caught:
            reject_forbidden_source(text)
        assert caught.value.reason == reason


def test_prose_about_shell_escape_is_allowed():
    parse_job(_job("do not enable shell-escape in this note.", input_kind="markdown"))
    parse_job(_job("Use -no-shell-escape only.", input_kind="markdown"))
    parse_job(_job("The word directlua is not a command.", input_kind="markdown"))
    parse_job(
        _job(
            "Mermaid and D2 are not rendered. The words mermaid and d2 stay prose.",
            input_kind="markdown",
        )
    )


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


def test_required_kind_fixtures_are_the_sold_candidate_set():
    """Document shell plus P&ID, circuits, plots, chemistry, Gantt, and floor plans."""
    kinds = FIXTURES / "kinds"
    names = sorted(path.name for path in kinds.iterdir())
    assert names == [
        "chemistry.md",
        "chemistry.tex",
        "circuits.md",
        "circuits.tex",
        "document-shell.md",
        "floorplan-scale.md",
        "floorplan-scale.tex",
        "floorplan.md",
        "floorplan.tex",
        "gantt.md",
        "gantt.tex",
        "pgfplots.md",
        "pgfplots.tex",
        "pidcircuit.md",
        "pidcircuit.tex",
    ]
    shell = (kinds / "document-shell.md").read_text(encoding="utf-8")
    assert "```" not in shell
    assert "\\documentclass" not in shell
    reject_forbidden_source(shell)
    for name in (
        "pidcircuit",
        "circuits",
        "pgfplots",
        "chemistry",
        "gantt",
        "floorplan",
    ):
        tex = (kinds / f"{name}.tex").read_text(encoding="utf-8")
        markdown = (kinds / f"{name}.md").read_text(encoding="utf-8")
        assert "\\documentclass" not in tex
        assert "```tikz" in markdown
        reject_forbidden_source(tex)
        reject_forbidden_source(markdown)
    plots = (kinds / "pgfplots.tex").read_text(encoding="utf-8")
    assert "\\addplot3" in plots
    assert "samples=2" in plots
    chemistry = (kinds / "chemistry.tex").read_text(encoding="utf-8")
    assert "\\chemfig" in chemistry
    assert "\\ce{" in chemistry
    half = (kinds / "floorplan-scale.tex").read_text(encoding="utf-8")
    assert "scale=0.5" in half
    assert "\\documentclass" not in half
    reject_forbidden_source(half)
    reject_forbidden_source((kinds / "pidcircuit.tex").read_text(encoding="utf-8"))


def test_unsold_packages_keep_a_smoke_compile_only():
    smoke = FIXTURES / "smoke"
    names = sorted(path.name for path in smoke.iterdir())
    assert names == [
        "automata.tex",
        "bytefield.tex",
        "forest.tex",
        "mindmap.tex",
        "tikz-3dplot.tex",
        "tikz-cd.tex",
        "tikz-feynman.tex",
        "tikz-timing.tex",
    ]
    for name in names:
        text = (smoke / name).read_text(encoding="utf-8")
        assert "\\documentclass" not in text
        reject_forbidden_source(text)
        assert not (FIXTURES / "kinds" / name).exists()
    feynman = (smoke / "tikz-feynman.tex").read_text(encoding="utf-8")
    assert "\\diagram*" in feynman
    assert "\\feynmandiagram" not in feynman
    assert "\\vertex" in feynman


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
        wrapper = (root / f"colophon/share/templates/{lane}/wrapper.tex").read_text(
            encoding="utf-8"
        )
        template = (root / f"colophon/share/templates/{lane}/pandoc.latex").read_text(
            encoding="utf-8"
        )
        assert "\\input{colophon-v1-preamble.tex}" in wrapper
        assert "\\input{colophon-v1-preamble.tex}" in template
        assert "\\usepackage{circuitikz}" not in wrapper
        assert "\\usepackage{circuitikz}" not in template
    lock = (root / "colophon/share/lock-diagram.lua").read_text(encoding="utf-8")
    assert "\\input{colophon-v1-preamble.tex}" in lock
    assert "mermaid" not in lock
    assert "mmdc" not in lock
    assert "d2:" not in lock
    diagram = (root / "vendor/diagram/diagram.lua").read_text(encoding="utf-8")
    assert "dgr_opt.opt[optname] = value" in diagram
    assert "dgr_opt.opt[optname] or value" not in diagram
    assert "local mermaid" not in diagram
    assert "local d2" not in diagram
    assert "mmdc" not in diagram
    assert "tikz      = tikz" in diagram


def test_image_recipe_drops_mermaid_and_d2():
    root = Path(__file__).resolve().parents[2]
    docker = (root / "container/Dockerfile.colophon").read_text(encoding="utf-8")
    for banned in (
        "nodejs",
        "npm install",
        "puppeteer",
        "mmdc-wrapper",
        "D2_VERSION",
        "MERMAID_CLI",
        "chromium \\",
    ):
        assert banned not in docker
    assert "must not be installed" in docker
    assert "command -v d2" in docker
    assert "command -v mmdc" in docker
    assert "command -v chromium" in docker
    assert not (root / "container/mmdc-wrapper").exists()
    assert not (root / "container/puppeteer.json").exists()
    assert not (root / "tests/colophon/fixtures/kinds/mermaid.md").exists()
    assert not (root / "tests/colophon/fixtures/kinds/d2.md").exists()
