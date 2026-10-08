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
# fence SYSMLTIKZ-R32-CLEAR from Endleaf PR 58, on the upright-item and
# human-header worker file, plus the SYSMLTIKZ-R33-FENCE text-overlap
# fence and SYSMLTIKZ-R33-OUTSIDE port labels (ENDLEAF-R55).
_ENDLEAF_STY_SHA256 = "84b3ad643c5ec84c0bb8af57f1043abbc1793129d0ecf12bd66517254bf09d56"
_PT_PER_MM = 72.27 / 25.4
_BOX = re.compile(
    r"SYSMLBOX (\S+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)"
)
_ITEM_MARK = re.compile(
    r"SYSMLMARK item rot=0 side=inline x=(-?[\d.]+)pt y=(-?[\d.]+)pt"
)
_ORIGIN = re.compile(r"SYSMLORIGIN x=(-?[\d.]+)pt y=(-?[\d.]+)pt")
_REVIEW = _ROOT / "tests/colophon/fixtures/review"
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


def test_style_fails_a_flow_item_that_cannot_clear_both_ports():
    text = _STY.read_text(encoding="utf-8")
    assert "SYSMLTIKZ-R32-CLEAR" in text
    assert "flow item cannot sit clear of both ports" in text
    assert r"\newcommand{\sysml@demandclear}" in text
    assert "sysml edge label, overlay, opacity=0" in text
    assert r"\setbox0=\hbox{\sysml@font" not in text
    assert r"\pgfinterruptpicture" not in text
    assert text.count(r"\sysml@demandclear") >= 3


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


def _standalone_sysml_tex(body):
    return (
        "\\documentclass{article}\n"
        "\\usepackage{sysml-tikz}\n"
        "\\pagestyle{empty}\n"
        "\\begin{document}\n"
        "\\makeatletter\\sysml@marktracetrue\\makeatother\n"
        "\\begin{sysmlfigure}[title={item clear}, body size={7}]\n"
        "\\begin{sysmlcanvas}\n"
        f"{body}\n"
        "\\end{sysmlcanvas}\n"
        "\\end{sysmlfigure}\n"
        "\\end{document}\n"
    )


def _run_xelatex(tmp_path, name, tex, halt=True):
    (tmp_path / name).write_text(tex, encoding="utf-8")
    env = os.environ.copy()
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    command = [
        "xelatex",
        "-no-shell-escape",
        "-interaction=nonstopmode",
        "-cnf-line=openin_any=p",
        name,
    ]
    if halt:
        command.insert(4, "-halt-on-error")
    completed = subprocess.run(
        command,
        cwd=tmp_path,
        check=False,
        timeout=120,
        capture_output=True,
        env=env,
    )
    log_path = tmp_path / Path(name).with_suffix(".log")
    log = (
        log_path.read_text(encoding="utf-8", errors="replace")
        if log_path.is_file()
        else completed.stdout.decode("utf-8", "replace")
    )
    return completed, log


def _parse_boxes(log):
    boxes = []
    for line in _unwrap_log(log).splitlines():
        match = _BOX.search(line)
        if match is None:
            continue
        boxes.append(
            {
                "kind": match.group(1),
                "x1": float(match.group(2)),
                "y1": float(match.group(3)),
                "x2": float(match.group(4)),
                "y2": float(match.group(5)),
            }
        )
    return boxes


def _overlaps(first, second):
    overlap_w = min(first["x2"], second["x2"]) - max(first["x1"], second["x1"])
    overlap_h = min(first["y2"], second["y2"]) - max(first["y1"], second["y1"])
    return overlap_w > 0.4 and overlap_h > 0.4


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_flow_item_that_clears_both_ports_still_compiles(tmp_path):
    body = (
        "\\sysmlpart{leftFrontWheel}{12}{28}{28}{16}\n"
        "\\sysmlport{leftFrontWheel.hub}{40}{36}{EAST}{30}{24}{hub0}{inout}\n"
        "\\sysmlpart{frontAxle}{78}{28}{36}{16}\n"
        "\\sysmlport{frontAxle.left}{78}{36}{WEST}{80}{24}{leftMountingPoint0}{inout}\n"
        "\\sysmlflow[from=frontAxle.left, to=leftFrontWheel.hub, "
        "item=transferredTorque]{vehicle.front.left}{(76.4,36) -- (41.6,36)}\n"
        "\\sysmlpart{M0.tank}{12}{56}{20}{12}\n"
        "\\sysmlport{M0.tank.out}{32}{62}{EAST}{34}{57}{out}{out}\n"
        "\\sysmlpart{M0.pump}{62}{56}{20}{12}\n"
        "\\sysmlport{M0.pump.in}{62}{62}{WEST}{50}{57}{in}{in}\n"
        "\\sysmlflow[from=M0.tank.out, to=M0.pump.in, at=mid, item=lvl]"
        "{M0.flow}{(33.6,62) -- (60.4,62)}\n"
    )
    completed, log = _run_xelatex(
        tmp_path, "clear.tex", _standalone_sysml_tex(body)
    )
    assert completed.returncode == 0, log[-1500:]
    assert "Missing character" not in log
    assert "flow item cannot sit clear of both ports" not in log
    measured = re.search(r"SYSMLMEAS labwd=([0-9.]+)", _unwrap_log(log))
    assert measured is not None
    assert float(measured.group(1)) > 1, measured.group(0)
    boxes = _parse_boxes(log)
    edges = [box for box in boxes if box["kind"] == "edge"]
    ports = [box for box in boxes if box["kind"] == "port"]
    assert len(edges) >= 2, f"edge marks {len(edges)}"
    assert len(ports) == 4
    for edge in edges:
        for port in ports:
            assert not _overlaps(edge, port), "item covers a port"
    item = _ITEM_MARK.search(_unwrap_log(log))
    origin = _ORIGIN.search(_unwrap_log(log))
    assert item is not None
    assert origin is not None
    mid_x = (76.4 + 41.6) / 2
    item_x_mm = (float(item.group(1)) - float(origin.group(1))) / _PT_PER_MM
    assert abs(item_x_mm - mid_x) < 1.2, f"C2 item at {item_x_mm}, expected {mid_x}"
    if shutil.which("pdftotext"):
        extracted = subprocess.run(
            ["pdftotext", "-raw", str(tmp_path / "clear.pdf"), "-"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert extracted.returncode == 0
        text = extracted.stdout
        assert "transferredTorque" in text
        assert "vehicle.front.left" not in text
        assert "M0.flow" not in text


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_flow_item_that_cannot_clear_both_ports_is_a_render_error(tmp_path):
    body = (
        "\\sysmlpart{L}{10}{20}{20}{12}\n"
        "\\sysmlport{L.p}{30}{26}{EAST}{22}{18}{hub0}{inout}\n"
        "\\sysmlpart{R}{42}{20}{20}{12}\n"
        "\\sysmlport{R.p}{42}{26}{WEST}{44}{18}{leftMountingPoint0}{inout}\n"
        "\\sysmlflow[from=R.p, to=L.p, item=transferredTorque]"
        "{short.flow}{(40.4,26) -- (31.6,26)}\n"
    )
    completed, log = _run_xelatex(
        tmp_path, "short.tex", _standalone_sysml_tex(body)
    )
    assert completed.returncode != 0
    assert "Package sysml-tikz Error: flow item cannot sit clear of both ports" in log
    assert "SYSMLMARK item " not in log


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_review_path_fixtures_still_compile(tmp_path):
    for name in ("midpoint-paths.tex", "v2-lines.tex"):
        tex = (_REVIEW / name).read_text(encoding="utf-8")
        if not _cjk_ready():
            tex = (
                tex.replace("\\usepackage{fontspec}\n", "")
                .replace("\\usepackage{xeCJK}\n", "")
                .replace("\\setCJKmainfont{Noto Sans CJK TC}\n", "")
                .replace("\\setmainfont{DejaVu Sans}\n", "")
            )
        completed, log = _run_xelatex(tmp_path, name, tex)
        assert completed.returncode == 0, log[-1500:]
        assert "flow item cannot sit clear of both ports" not in log


# SYSMLTIKZ-R33-FENCE. Owner sheet the live service returned as ok on
# 2026-10-08: overlapping text is a typed render error, not an ok PDF.
_SYSML_FIXTURES = _ROOT / "tests/colophon/fixtures/sysml"


def _compose_sysml(_tmp_path, body):
    tex = compose("sysml", "Weft", body, _OWNED)
    if not _cjk_ready():
        tex = (
            tex.replace("\\usepackage{fontspec}\n", "")
            .replace("\\usepackage{xeCJK}\n", "")
            .replace("\\setCJKmainfont{Noto Sans CJK TC}\n", "")
            .replace("\\input{endleaf-type.tex}\n", "")
        )
    return tex


def _fence_hits(tmp_path, body):
    """Run without halting and with traces on, so every hit is logged."""
    tex = _standalone_sysml_tex(body)
    completed, log = _run_xelatex(tmp_path, "hits.tex", tex, halt=False)
    return completed, re.findall(r"SYSMLHIT (.+)", _unwrap_log(log))


def test_style_declares_the_overlap_fence():
    text = _STY.read_text(encoding="utf-8")
    assert "SYSMLTIKZ-R33-FENCE" in text
    assert "SYSMLTIKZ-R33-OUTSIDE" in text
    assert r"\newcommand{\sysml@canvascheck}" in text
    assert "execute at end picture={\\sysml@canvascheck}" in text
    assert "{layout_overlap}" in text
    assert "{line_into_port}" in text


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_owner_overlap_sheet_is_a_render_error(tmp_path):
    body = (_SYSML_FIXTURES / "ei-source-overlap.tex").read_text(encoding="utf-8")
    completed, log = _run_xelatex(tmp_path, "job.tex", _compose_sysml(tmp_path, body))
    assert completed.returncode != 0
    text = _unwrap_log(log)
    assert "Package sysml-tikz Error: layout_overlap: " in text
    assert re.search(r"\(\+\d+ more\)", text)
    assert not (tmp_path / "job.pdf").is_file()


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_owner_overlap_sheet_names_each_reported_fault(tmp_path):
    body = (_SYSML_FIXTURES / "ei-source-overlap.tex").read_text(encoding="utf-8")
    body = "\\makeatletter\\sysml@marktracetrue\\makeatother\n" + body
    tex = _compose_sysml(tmp_path, body)
    _completed, log = _run_xelatex(tmp_path, "job.tex", tex, halt=False)
    hits = re.findall(r"SYSMLHIT (.+)", _unwrap_log(log))
    assert "layout_overlap: keyword at 94.2,147.6 on label of S.opt.tBias" in hits
    assert "layout_overlap: type ElectronImpactIonSource on label of S.ion.eCol" in hits
    assert "layout_overlap: label of S.drv.fil on box S.drv" in hits
    assert "layout_overlap: keyword at 13.3,31.6 on port S.ms.eth" in hits


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_owner_sheet_laid_out_clean_still_compiles(tmp_path):
    body = (_SYSML_FIXTURES / "ei-source-clean.tex").read_text(encoding="utf-8")
    completed, log = _run_xelatex(tmp_path, "job.tex", _compose_sysml(tmp_path, body))
    assert completed.returncode == 0, _unwrap_log(log)[-1500:]
    assert "layout_overlap" not in log
    assert "line_into_port" not in log


_TWO = (
    "\\sysmlpart{A}{0}{0}{20}{14}"
    "\\sysmlport{A.o}{20}{7}{EAST}{}{}{out}{out}"
    "\\sysmlpart{B}{50}{0}{20}{14}"
    "\\sysmlport{B.i}{50}{7}{WEST}{}{}{in}{in}\n"
)


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_line_into_a_port_square_is_a_render_error(tmp_path):
    body = _TWO + "\\sysmlflow[from=A.o, to=B.i]{f}{(21.6,7) -- (50,7)}\n"
    _completed, hits = _fence_hits(tmp_path, body)
    assert hits == ["line_into_port: line f into port B.i"]
    body = _TWO + "\\sysmlflow[from=A.o, to=B.i]{f}{(21.6,7) -- (48.4,7)}\n"
    completed, hits = _fence_hits(tmp_path, body)
    assert hits == []
    assert completed.returncode == 0


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_text_on_a_line_or_an_end_head_is_a_render_error(tmp_path):
    body = _TWO + "\\sysmllabel[name]{35}{4}{Hello}\\sysmlconnection{c}{(35,1) -- (35,12)}\n"
    _completed, hits = _fence_hits(tmp_path, body)
    assert hits == ["layout_overlap: name Hello on line c"]
    body = _TWO + "\\sysmllabel[name]{35}{4}{Hello}\\sysmlconnection{c}{(30,1) -- (40,12)}\n"
    _completed, hits = _fence_hits(tmp_path, body)
    assert hits == ["layout_overlap: name Hello on line c"]
    body = (
        _TWO.replace("{WEST}{}{}{in}", "{WEST}{44}{5.6}{in}")
        + "\\sysmlflow[from=A.o, to=B.i]{f}{(21.6,7) -- (48.4,7)}\n"
    )
    _completed, hits = _fence_hits(tmp_path, body)
    assert "layout_overlap: label of B.i on head of f" in hits


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_empty_label_point_puts_port_labels_outside_the_part(tmp_path):
    body = (
        "\\sysmlpart{A}{0}{10}{30}{14}"
        "\\sysmllabel[keyword]{15}{13}{\\sysmlguillemets{part}}"
        "\\sysmlport{A.n}{15}{10}{NORTH}{}{}{tBias}{in}"
        "\\sysmlport{A.s}{15}{24}{SOUTH}{}{}{sOut}{out}"
        "\\sysmlport{A.w}{0}{17}{WEST}{}{}{wIn}{in}"
        "\\sysmlport{A.e}{30}{17}{EAST}{}{}{eOut}{out}\n"
    )
    completed, log = _run_xelatex(tmp_path, "auto.tex", _standalone_sysml_tex(body))
    assert completed.returncode == 0, _unwrap_log(log)[-1500:]
    boxes = _parse_boxes(log)
    part = next(box for box in boxes if box["kind"] == "part")
    labels = [box for box in boxes if box["kind"] == "plab"]
    assert len(labels) == 4
    for label in labels:
        assert not _overlaps(label, part), label
