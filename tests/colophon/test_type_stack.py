# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Owner lock: one type stack on every human-facing PDF."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.templates import ALLOWED_INPUTS, TEMPLATE_IDS, compose

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"
_SHARE = _ROOT / "colophon/share"
_TYPE = _ROOT / "colophon/share/tex/latex/colophon-v1/endleaf-type.tex"
_TEXINPUTS = os.pathsep.join(
    (
        str(_ROOT / "colophon/share/tex/latex/colophon-v1"),
        str(_ROOT / "colophon/share/tex/latex/endleaf-floorplan"),
        str(_ROOT / "colophon/share/tex/latex/sysml-tikz"),
        str(_ROOT / "vendor/pidcircuittikz"),
        "",
    )
)


def _type_ready():
    if shutil.which("xelatex") is None or shutil.which("pdffonts") is None:
        return False
    if shutil.which("kpsewhich") is None:
        return False
    found = subprocess.run(
        ["kpsewhich", "texgyrepagella-regular.otf"],
        check=False,
        capture_output=True,
        text=True,
    )
    return found.returncode == 0 and bool(found.stdout.strip())


def test_templates_input_endleaf_type_after_cjk():
    assert "endleaf-type.tex" in ALLOWED_INPUTS
    text = _TYPE.read_text(encoding="utf-8")
    assert "texgyrepagella" in text
    assert "texgyreheros" in text
    assert "texgyrecursor" in text
    assert "\\usepackage{tgpagella}" not in text
    assert "\\setCJKmainfont" not in text
    assert "\\usepackage{xeCJK}" not in text
    for template_id in TEMPLATE_IDS:
        preamble = (_OWNED / template_id / "preamble.tex").read_text(encoding="utf-8")
        assert "\\input{endleaf-type.tex}" in preamble
        assert preamble.index("\\setCJKmainfont{Noto Sans CJK TC}") < preamble.index(
            "\\input{endleaf-type.tex}"
        )
    for lane in ("InstruMeasure", "Weft", "Investor"):
        for name in ("wrapper.tex", "pandoc.latex"):
            blob = (_SHARE / "templates" / lane / name).read_text(encoding="utf-8")
            assert "\\input{endleaf-type.tex}" in blob
            assert blob.index("\\setCJKmainfont{Noto Sans CJK TC}") < blob.index(
                "\\input{endleaf-type.tex}"
            )
            assert blob.index("\\input{endleaf-type.tex}") < blob.index(
                "\\input{colophon-v1-preamble.tex}"
            )
    lua = (_SHARE / "lock-diagram.lua").read_text(encoding="utf-8")
    assert lua.index("\\setCJKmainfont{Noto Sans CJK TC}") < lua.index(
        "\\input{endleaf-type.tex}"
    )
    assert lua.index("\\input{endleaf-type.tex}") < lua.index(
        "\\input{colophon-v1-preamble.tex}"
    )


@pytest.mark.skipif(not _type_ready(), reason="xelatex or TeX Gyre Pagella is not installed")
def test_composed_body_uses_pagella_heros_cursor_not_cmr(tmp_path):
    """pdffonts on a live PDF must show Pagella/Heros/Cursor, not CMR for body."""
    body = (
        "Body prose.\n\n"
        "{\\sffamily Diagram UI}\n\n"
        "{\\ttfamily PdMon.pump}\n"
    )
    tex = compose("document-shell", "Weft", body, _OWNED)
    assert "\\input{endleaf-type.tex}" in tex
    work = tmp_path / "type-stack"
    work.mkdir()
    (work / "job.tex").write_text(tex, encoding="utf-8")
    env = os.environ.copy()
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    completed = subprocess.run(
        [
            "xelatex",
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "job.tex",
        ],
        cwd=work,
        check=False,
        timeout=90,
        capture_output=True,
        env=env,
    )
    log = (work / "job.log").read_text(encoding="utf-8", errors="replace")
    assert completed.returncode == 0, log[-2000:]
    pdf = work / "job.pdf"
    assert pdf.is_file()
    fonts = subprocess.run(
        ["pdffonts", str(pdf)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert fonts.returncode == 0, fonts.stderr
    blob = fonts.stdout.lower().replace("-", "").replace(" ", "")
    assert "pagella" in blob
    assert "heros" in blob
    assert "cursor" in blob
    for banned in ("cmr", "lmroman", "latinmodernroman"):
        assert banned not in blob, fonts.stdout
