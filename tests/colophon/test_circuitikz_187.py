# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R75: the worker image carries circuitikz 1.8.7 and its new symbols compile."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.templates import compose
from tests.colophon.test_sysml_tikz import _cjk_ready

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"
_DOCKERFILE = _ROOT / "container/Dockerfile.endleaf"
_SYMBOLS = _ROOT / "tests/colophon/fixtures/circuitikz-new-symbols.json"
_VERSION = "1.8.7"
_SHA256 = "768edfc7d4cbe77145790f5e4fee929437364c9e359ab3d8a04a2dad1593fd9c"
_TEXINPUTS = os.pathsep.join(
    (
        str(_ROOT / "colophon/share/tex/latex/colophon-v1"),
        str(_ROOT / "colophon/share/tex/latex/endleaf-floorplan"),
        str(_ROOT / "colophon/share/tex/latex/sysml-tikz"),
        str(_ROOT / "vendor/pidcircuittikz"),
        "",
    )
)
# Symbols already on the old circuitikz that the PID library once hid.
_KNOWN = ("spring", "damper", "crossing")
_PER_PICTURE = 20
_COLUMNS = 4
_ERRORS = (
    "I do not know the key",
    "Unknown shape",
    "Package pgfkeys Error",
    "Undefined control sequence",
)

# Reports a name nothing defines. A to[...] key is a /tikz style; a node name
# is a shape or, for the blank ports, a style.
_PROBES = r"""\makeatletter
\newcommand\CKMISS[3]{\typeout{MISSING|#1}\node[draw=red,text=red] at (#2,#3) {missing};}
\newcommand\CKP[4]{\pgfkeysifdefined{/tikz/#1/.@cmd}{#2}{\CKMISS{#1}{#3}{#4}}}
\newcommand\CKN[4]{\pgfutil@ifundefined{pgf@sh@s@#1}{\pgfkeysifdefined{/tikz/#1/.@cmd}{#2}{\CKMISS{#1}{#3}{#4}}}{#2}}
\makeatother
\typeout{CTZVER|\pgfcircversion}
"""


def _symbols():
    return json.loads(_SYMBOLS.read_text(encoding="utf-8"))


def _body(paths, nodes):
    pictures = []
    items = [("P", name) for name in paths] + [("N", name) for name in nodes]
    for start in range(0, len(items), _PER_PICTURE):
        lines = ["\\begin{circuitikz}"]
        for index, (kind, name) in enumerate(items[start : start + _PER_PICTURE]):
            x = (index % _COLUMNS) * 3.0
            y = -(index // _COLUMNS) * 2.0
            if kind == "P":
                draw = "\\draw (%s,%s) to[%s] (%s,%s);" % (x - 1.1, y, name, x + 1.1, y)
            else:
                draw = "\\node[%s] at (%s,%s) {};" % (name, x, y)
            lines.append("  \\CK%s{%s}{%s}{%s}{%s}" % (kind, name, "{%s}" % draw, x, y))
        lines.append("\\end{circuitikz}")
        pictures.append("\n".join(lines))
    return _PROBES + "\n\\clearpage\n".join(pictures) + "\n"


def _compile(tmp_path, body):
    tex = compose("circuits", "lane-a", body, _OWNED)
    if not _cjk_ready():
        tex = (
            tex.replace("\\usepackage{fontspec}\n", "")
            .replace("\\usepackage{xeCJK}\n", "")
            .replace("\\setCJKmainfont{Noto Sans CJK TC}\n", "")
            .replace("\\input{endleaf-type.tex}\n", "")
        )
    (tmp_path / "job.tex").write_text(tex, encoding="utf-8")
    env = os.environ.copy()
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    subprocess.run(
        ["xelatex", "-no-shell-escape", "-interaction=nonstopmode", "-cnf-line=openin_any=p", "job.tex"],
        cwd=tmp_path,
        check=False,
        timeout=600,
        capture_output=True,
        env=env,
    )
    log_path = tmp_path / "job.log"
    return log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""


def _check(tmp_path, paths, nodes):
    log = _compile(tmp_path, _body(paths, nodes))
    version = re.search(r"CTZVER\|(\S+)", log)
    if version is None or version.group(1) != _VERSION:
        pytest.skip("circuitikz %s is not installed here; run in the worker image" % _VERSION)
    assert (tmp_path / "job.pdf").is_file(), log[-1500:]
    missing = sorted(set(re.findall(r"MISSING\|(.+)", log)))
    assert not missing, "missing shapes or keys: %s" % missing
    errors = [line for line in log.splitlines() if any(text in line for text in _ERRORS)]
    assert not errors, errors[:10]


def test_fixture_lists_are_complete():
    data = _symbols()
    assert len(data["paths"]) == 73
    assert len(data["aliases"]) == 109
    assert len(data["nodes"]) == 22
    for name in ("blank port", "european blank not port", "iecplugL", "iecsocketR"):
        assert name in data["nodes"]
    for name in ("sinetable", "wiggly fuse", "iecconn"):
        assert name in data["paths"]
    for key in ("paths", "aliases", "nodes"):
        assert len(set(data[key])) == len(data[key])


def test_dockerfile_pins_the_ctan_release_in_texmflocal():
    text = _DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG CIRCUITIKZ_VERSION=%s\n" % _VERSION in text
    assert "ARG CIRCUITIKZ_SHA256=%s\n" % _SHA256 in text
    assert "sha256sum -c -" in text
    assert "/usr/local/share/texmf/tex/latex/circuitikz" in text
    # The build fails unless the compiled \pgfcircversion is the pinned one.
    assert "\\typeout{CTZVER|\\pgfcircversion}" in text
    assert 'grep -qF "CTZVER|${CIRCUITIKZ_VERSION}"' in text
    # The copy in TEXMFLOCAL must be the one kpathsea finds first.
    assert 'test "$(kpsewhich circuitikz.sty)" = /usr/local/share/texmf/tex/latex/circuitikz/circuitikz.sty' in text


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_new_circuitikz_symbols_compile_without_missing_shapes(tmp_path):
    data = _symbols()
    _check(tmp_path, data["paths"] + data["aliases"], data["nodes"])


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_spring_damper_crossing_compile(tmp_path):
    _check(tmp_path, list(_KNOWN), [])


def test_preamble_does_not_shrink_the_gate_marks():
    # The circuitikz european gate marks (&, >=1, =1) use `european ports font`,
    # empty by default, so they follow the 10 pt class size. The TikZ
    # circuits.logic.IEC marks are \scriptstyle, 7 pt at 10 pt. Nothing in the
    # preamble may set either smaller.
    shared = _ROOT / "colophon/share/tex/latex/colophon-v1"
    for name in ("colophon-v1-preamble.tex", "endleaf-kinds.tex", "endleaf-type.tex"):
        assert "european ports font" not in (shared / name).read_text(encoding="utf-8"), name
    preamble = (_OWNED / "circuits" / "preamble.tex").read_text(encoding="utf-8")
    assert "\\documentclass[__PAPER__]{article}" in preamble
