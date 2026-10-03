# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""sysml-tikz is on the document-shell allowlist and the kind fixture compiles."""

import hashlib
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
    "sysmlflow",
    "sysmlbinding",
    "sysmllabel",
    "sysmlguillemets",
)
_FIXTURE_COMMANDS = tuple(name for name in _COMMANDS if name != "sysmldef")
_ENVS = ("sysmlfigure", "sysmlcanvas")


def test_allowlist_accepts_sysml_tikz():
    assert "sysml-tikz" in ALLOWED_PACKAGES
    preamble = (
        _ROOT / "colophon/share/tex/latex/colophon-v1/colophon-v1-preamble.tex"
    ).read_text(encoding="utf-8")
    assert "\\usepackage{sysml-tikz}" in preamble
    shell = (_OWNED / "document-shell" / "preamble.tex").read_text(encoding="utf-8")
    assert "\\input{colophon-v1-preamble.tex}" in shell
    assert "\\input{endleaf-type.tex}" in shell


# Worker copy of Endleaf prototypes/sysml-layout/sysml-tikz.sty
# at 65baacff166cdee7b3393bc27a01e5d80ad1262f, with upright item
# text and a human sysmlfigure header.
_ENDLEAF_STY_SHA256 = "d8c0caffec0a19c144e3ae54952bf6a55026ea336316aa84503cecc7a4d591e7"
_LAB = re.compile(
    r"SYSMLLAB\s+(\S+)\s+fill=\S+\s+lx=\S+\s+ly=\S+\s+"
    r"wx=\S+\s+ex=\S+\s+upright=([01])"
)


def test_vendored_style_matches_endleaf_and_requires_only_tikz():
    data = _STY.read_bytes()
    assert hashlib.sha256(data).hexdigest() == _ENDLEAF_STY_SHA256
    text = data.decode("utf-8")
    assert "\\ProvidesPackage{sysml-tikz}" in text
    assert "\\newcommand{\\sysmlconnection}[3][]" in text
    assert "\\newcommand{\\sysmlflow}[3][]" in text
    assert "\\newcommand{\\sysmlbinding}[3][]" in text
    assert "A connection is a plain solid line" in text
    assert "sysml connection/.style={draw, line width=0.45pt}" in text
    assert (
        "sysml flow end/.style={draw, line width=0.45pt, "
        "-{Triangle[length=3.2mm,width=2.6mm,sep=0pt]}}"
    ) in text
    requires = re.findall(r"\\RequirePackage(?:\[[^\]]*\])?\{([^}]+)\}", text)
    assert requires == ["tikz"]
    for name in _COMMANDS:
        assert "\\" + name in text
    for name in _ENVS:
        assert "\\newenvironment{" + name + "}" in text


def test_style_keeps_item_text_upright_and_hides_header_chrome():
    text = _STY.read_text(encoding="utf-8")
    assert r"\newcommand{\sysml@keepupright}" in text
    assert r"\pgftransformresetnontranslations" in text
    assert text.count(r"\sysml@keepupright") >= 3
    assert r"\newcommand{\sysml@heading}" in text
    assert r"title/.initial={}" in text
    assert r"View \texttt{\pgfkeysvalueof{/sysml/view}}" not in text
    assert r"overrides \texttt{\pgfkeysvalueof{/sysml/overrides}}" not in text
    assert r"depth \texttt{\pgfkeysvalueof{/sysml/depth}}" not in text
    assert r"type \texttt{\sysml@body}" not in text
    assert r"body size/.code" in text


def test_sysml_kind_fixture_uses_sty_macros():
    text = _FIXTURE.read_text(encoding="utf-8")
    markdown = (_FIXTURE.with_suffix(".md")).read_text(encoding="utf-8")
    assert "```tikz" in markdown
    assert text.strip() in markdown
    for name in _FIXTURE_COMMANDS:
        assert "\\" + name in text
    for name in _ENVS:
        assert "\\begin{" + name + "}" in text
    assert text.count("\\sysmlpart") == 3
    assert "\\sysmlconnection[from=PdMon.pump.outlet, to=PdMon.motor.inlet]" in text
    assert (
        "\\sysmlflow[from=PdMon.motor.outlet, to=PdMon.ctrl.inlet, item=液位]" in text
    )
    assert "\\sysmlbinding[from=PdMon.pump.bind, to=PdMon.motor.bind]" in text
    assert "{in}" in text
    assert "{out}" in text
    assert "{inout}" in text
    assert "幫浦" in text
    assert "连接" not in text
    assert "绑定" not in text
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
            .replace("\\input{endleaf-type.tex}\n", "")
        )
    elif shutil.which("kpsewhich"):
        gyre = subprocess.run(
            ["kpsewhich", "texgyrepagella-regular.otf"],
            check=False,
            capture_output=True,
        )
        if gyre.returncode != 0 or not gyre.stdout.strip():
            tex = tex.replace("\\input{endleaf-type.tex}\n", "")
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
        assert "幫浦" in extracted.stdout
        assert "View" not in extracted.stdout
        assert "overrides" not in extracted.stdout
        assert not re.search(r"type\s+\d+\s*pt", extracted.stdout)


def _unwrap_log(log):
    pieces = []
    pending = ""
    for line in log.splitlines():
        pending = pending + line if pending else line
        if len(line) < 79:
            pieces.append(pending)
            pending = ""
    if pending:
        pieces.append(pending)
    return "\n".join(pieces)


def _shipped_item_upright(log):
    text = _unwrap_log(log)
    start = text.rfind("ENDLEAF_FIT_SHIP")
    if start < 0:
        start = 0
    return _LAB.findall(text[start:])


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_flow_item_stays_upright_when_path_is_reversed(tmp_path):
    body = (
        "\\makeatletter\\sysml@marktracetrue\\makeatother\n"
        "\\begin{sysmlfigure}[title={leftFrontMount}, revision={vehicle-C2}, "
        "overrides={none}, depth={1}, body size={10}]\n"
        "\\begin{sysmlcanvas}\n"
        "\\sysmlpart{L.box}{8}{8}{20}{12}\n"
        "\\sysmlport{L.out}{28}{14}{EAST}{30}{8}{out}{out}\n"
        "\\sysmlpart{R.box}{80}{8}{20}{12}\n"
        "\\sysmlport{R.in}{80}{14}{WEST}{68}{8}{in}{in}\n"
        "\\sysmlflow[from=L.out, to=R.in, item=ltrTorque]{L.flow}"
        "{(29.6,14) -- (78.4,14)}\n"
        "\\sysmlpart{RL.box}{8}{40}{20}{12}\n"
        "\\sysmlport{RL.out}{28}{46}{EAST}{30}{40}{out}{out}\n"
        "\\sysmlpart{RR.box}{80}{40}{20}{12}\n"
        "\\sysmlport{RR.in}{80}{46}{WEST}{68}{40}{in}{in}\n"
        "\\sysmlflow[from=RL.out, to=RR.in, item=transferredTorque]{R.flow}"
        "{(78.4,46) -- (29.6,46)}\n"
        "\\end{sysmlcanvas}\n"
        "\\end{sysmlfigure}\n"
    )
    tex = compose("sysml", "Weft", body, _OWNED)
    if not _cjk_ready():
        tex = (
            tex.replace("\\usepackage{fontspec}\n", "")
            .replace("\\usepackage{xeCJK}\n", "")
            .replace("\\setCJKmainfont{Noto Sans CJK TC}\n", "")
            .replace("\\input{endleaf-type.tex}\n", "")
        )
    elif shutil.which("kpsewhich"):
        gyre = subprocess.run(
            ["kpsewhich", "texgyrepagella-regular.otf"],
            check=False,
            capture_output=True,
        )
        if gyre.returncode != 0 or not gyre.stdout.strip():
            tex = tex.replace("\\input{endleaf-type.tex}\n", "")
    (tmp_path / "flow.tex").write_text(tex, encoding="utf-8")
    env = os.environ.copy()
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    completed = subprocess.run(
        [
            "xelatex",
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-cnf-line=openin_any=p",
            "flow.tex",
        ],
        cwd=tmp_path,
        check=False,
        timeout=120,
        capture_output=True,
        env=env,
    )
    log_path = tmp_path / "flow.log"
    log = (
        log_path.read_text(encoding="utf-8", errors="replace")
        if log_path.is_file()
        else completed.stdout.decode("utf-8", "replace")
    )
    assert completed.returncode == 0, log[-1500:]
    items = [kind for kind, _upright in _shipped_item_upright(log) if kind == "item"]
    upright = [
        flag for kind, flag in _shipped_item_upright(log) if kind == "item"
    ]
    assert items == ["item", "item"], log[-2000:]
    assert upright == ["1", "1"], log[-2000:]
    if shutil.which("pdftotext"):
        extracted = subprocess.run(
            ["pdftotext", "-raw", str(tmp_path / "flow.pdf"), "-"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert extracted.returncode == 0
        text = extracted.stdout
        assert "ltrTorque" in text
        assert "transferredTorque" in text
        assert "leftFrontMount" in text
        assert "vehicle-C2" in text
        assert "View" not in text
        assert "overrides" not in text
        assert "depth" not in text
        assert not re.search(r"type\s+10\s*pt", text)
