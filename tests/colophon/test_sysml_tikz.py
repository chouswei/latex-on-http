# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""sysml-tikz is on the document-shell allowlist and the kind fixture compiles."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.templates import ALLOWED_PACKAGES, compose

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"
_STY = _ROOT / "colophon/share/tex/latex/sysml-tikz/sysml-tikz.sty"
_FIXTURE = _ROOT / "tests/colophon/fixtures/kinds/sysml.tex"
_TEXINPUTS = os.pathsep.join(
    (
        str(_ROOT / "colophon/share/tex/latex/colophon-v1"),
        str(_ROOT / "colophon/share/tex/latex/endleaf-floorplan"),
        str(_ROOT / "colophon/share/tex/latex/sysml-tikz"),
        str(_ROOT / "vendor/pidcircuittikz"),
        "",
    )
)
_COMMANDS = (
    "sysmldef",
    "sysmlpart",
    "sysmlport",
    "sysmlconnection",
    "sysmllabel",
    "sysmlguillemets",
)
_ENVS = ("sysmlfigure", "sysmlcanvas")


def test_allowlist_accepts_sysml_tikz():
    assert "sysml-tikz" in ALLOWED_PACKAGES
    preamble = (
        _ROOT / "colophon/share/tex/latex/colophon-v1/colophon-v1-preamble.tex"
    ).read_text(encoding="utf-8")
    assert "\\usepackage{sysml-tikz}" in preamble
    shell = (_OWNED / "document-shell" / "preamble.tex").read_text(encoding="utf-8")
    assert "\\input{colophon-v1-preamble.tex}" in shell


def test_vendored_style_records_source_and_requires_only_tikz():
    text = _STY.read_text(encoding="utf-8")
    assert "prototypes/sysml-layout/sysml-tikz.sty" in text
    assert "7462a3188850852c47ca2c0cb5c43143ba6a0b27" in text
    assert "\\ProvidesPackage{sysml-tikz}" in text
    requires = re.findall(r"\\RequirePackage(?:\[[^\]]*\])?\{([^}]+)\}", text)
    assert requires == ["tikz"]
    for name in _COMMANDS:
        assert "\\" + name in text
    for name in _ENVS:
        assert "\\newenvironment{" + name + "}" in text


def test_sysml_kind_fixture_uses_sty_macros():
    text = _FIXTURE.read_text(encoding="utf-8")
    markdown = (_FIXTURE.with_suffix(".md")).read_text(encoding="utf-8")
    assert "```tikz" in markdown
    assert text.strip() in markdown
    for name in _COMMANDS:
        assert "\\" + name in text
    for name in _ENVS:
        assert "\\begin{" + name + "}" in text
    assert text.count("\\sysmlpart") == 2
    assert "\\sysmldef" in text
    assert "\\sysmlconnection" in text
    assert "{in}" in text
    assert "{out}" in text
    assert "{inout}" in text
    assert "泵浦" in text
    assert "\\documentclass" not in text
    assert "\\usepackage" not in text


def _cjk_ready():
    if shutil.which("kpsewhich") is None or shutil.which("fc-list") is None:
        return False
    found = subprocess.run(
        ["kpsewhich", "xeCJK.sty"],
        check=False,
        capture_output=True,
    )
    if found.returncode != 0:
        return False
    fonts = subprocess.run(
        ["fc-list", ":family"],
        check=False,
        capture_output=True,
        text=True,
    )
    return "Noto Sans CJK TC" in fonts.stdout


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_sysml_kind_fixture_compiles(tmp_path):
    body = _FIXTURE.read_text(encoding="utf-8")
    tex = compose("sysml", "Weft", body, _OWNED)
    assert "\\usepackage{sysml-tikz}" in (
        _ROOT / "colophon/share/tex/latex/colophon-v1/colophon-v1-preamble.tex"
    ).read_text(encoding="utf-8")
    if not _cjk_ready():
        tex = (
            tex.replace("\\usepackage{fontspec}\n", "")
            .replace("\\usepackage{xeCJK}\n", "")
            .replace("\\setCJKmainfont{Noto Sans CJK TC}\n", "")
        )
    (tmp_path / "sysml.tex").write_text(tex, encoding="utf-8")
    env = os.environ.copy()
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    completed = subprocess.run(
        [
            "xelatex",
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-cnf-line=openin_any=p",
            "sysml.tex",
        ],
        cwd=tmp_path,
        check=False,
        timeout=120,
        capture_output=True,
        env=env,
    )
    log_path = tmp_path / "sysml.log"
    log = (
        log_path.read_text(encoding="utf-8", errors="replace")
        if log_path.is_file()
        else completed.stdout.decode("utf-8", "replace")
    )
    assert completed.returncode == 0, log[-1500:]
    assert (tmp_path / "sysml.pdf").is_file()
    assert "sysml-tikz.sty" in log
    if _cjk_ready() and shutil.which("pdftotext"):
        extracted = subprocess.run(
            ["pdftotext", "-raw", str(tmp_path / "sysml.pdf"), "-"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert extracted.returncode == 0
        assert "泵浦" in extracted.stdout
