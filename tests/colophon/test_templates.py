# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R27. templateId plus body, server-owned preambles."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.enums import JobRejected, parse_job
from colophon.templates import (
    ALLOWED_CLASSES,
    ALLOWED_INPUTS,
    ALLOWED_LIBRARIES,
    ALLOWED_PACKAGES,
    TEMPLATE_IDS,
    compose,
    example_body,
)
from tests.colophon.conftest import valid_body

_ROOT = (
    Path(__file__).resolve().parents[2] / "colophon" / "share" / "templates" / "owned"
)
_TEXINPUTS = os.pathsep.join(
    (
        str(
            Path(__file__).resolve().parents[2] / "colophon/share/tex/latex/colophon-v1"
        ),
        str(
            Path(__file__).resolve().parents[2]
            / "colophon/share/tex/latex/endleaf-floorplan"
        ),
        str(
            Path(__file__).resolve().parents[2] / "colophon/share/tex/latex/sysml-tikz"
        ),
        str(Path(__file__).resolve().parents[2] / "vendor/pidcircuittikz"),
        "",
    )
)


def test_unknown_template_id_is_refused(client, auth, runner):
    response = client.post(
        "/v1/jobs",
        json=valid_body(templateId="not-a-template"),
        headers=auth,
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "rejectInvalidInput"
    assert body["field"] == "templateId"
    assert body["result"] == "refused"
    assert runner.calls == []


def test_documentclass_in_every_template_body_is_refused():
    for template_id in TEMPLATE_IDS:
        with pytest.raises(JobRejected) as caught:
            parse_job(
                valid_body(
                    templateId=template_id,
                    body="\\documentclass{article}\nHello.",
                )
            )
        assert caught.value.reason == "documentclass"


def _assert_allowlist(text):
    for name in re.findall(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", text):
        assert name in ALLOWED_CLASSES
    for name in re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", text):
        assert name in ALLOWED_PACKAGES
    for name in re.findall(r"\\input\{([^}]+)\}", text):
        assert name in ALLOWED_INPUTS
    for group in re.findall(r"\\usetikzlibrary\{([^}]+)\}", text):
        for name in group.split(","):
            assert name.strip() in ALLOWED_LIBRARIES


def test_preambles_use_only_the_allowlist():
    for template_id in TEMPLATE_IDS:
        text = (_ROOT / template_id / "preamble.tex").read_text(encoding="utf-8")
        if template_id == "fulldoc":
            assert "\\documentclass[10pt,__PAPER__]{article}" in text
        elif template_id == "sysml":
            assert "\\documentclass[__PAPER__]{article}" in text
            assert "\\input{endleaf-fit.tex}" in text
            after_begin = text.split("\\begin{document}", 1)[1]
            assert "\\begin{minipage}" not in after_begin
            assert "\\pdfpagewidth=" not in after_begin
        elif template_id == "document-shell":
            assert "\\documentclass[10pt,__PAPER__]{article}" in text
        else:
            assert "\\documentclass[__PAPER__]{article}" in text
        assert text.count("__PAPER__") == 1
        assert "\\usepackage{fontspec}" in text
        assert "\\input{endleaf-type.tex}" in text
        assert text.index("\\setCJKmainfont{Noto Sans CJK TC}") < text.index(
            "\\input{endleaf-type.tex}"
        )
        if template_id == "fulldoc":
            assert "\\input{colophon-v1-preamble.tex}" not in text
            assert "\\input{endleaf-fit.tex}" in text
            assert "\\input{endleaf-credit.tex}" in text
            assert text.index("\\input{endleaf-credit.tex}") < text.index(
                "\\begin{document}"
            )
            assert "\\setlength{\\belowcaptionskip}{4pt}" in text
            assert "\\setlength\\@fptop{0pt}" in text
            sep = re.search(r"\\setlength\\@fpsep\{([^}]*)\}", text)
            assert sep is not None and sep.group(1) == "12pt"
            assert "\\setlength\\@fpbot{0pt plus 1fil}" in text
            for banned in (
                "\\usepackage{geometry}",
                "\\usepackage{needspace}",
                "\\usepackage{float}",
                "\\usepackage{caption}",
            ):
                assert banned not in text
        else:
            assert "\\input{colophon-v1-preamble.tex}" in text
        _assert_allowlist(text)
    shared = (
        Path(__file__).resolve().parents[2]
        / "colophon/share/tex/latex/colophon-v1/colophon-v1-preamble.tex"
    ).read_text(encoding="utf-8")
    _assert_allowlist(shared)
    type_stack = (
        Path(__file__).resolve().parents[2]
        / "colophon/share/tex/latex/colophon-v1/endleaf-type.tex"
    ).read_text(encoding="utf-8")
    _assert_allowlist(type_stack)
    assert "texgyrepagella" in type_stack
    assert "texgyreheros" in type_stack
    assert "texgyrecursor" in type_stack
    assert "\\setCJKmainfont" not in type_stack
    assert "\\usepackage{xeCJK}" not in type_stack
    assert "7 pt" in type_stack or "7pt" in type_stack


def test_gantt_example_does_not_end_the_last_bar_with_a_row_break():
    body = example_body("gantt", _ROOT)
    assert r"\ganttbar[name=build]{建置 Build}{6}{11}" in body
    assert r"\ganttbar[name=build]{建置 Build}{6}{11} \\" not in body


def test_floorplan_example_places_the_scale_bar_once():
    body = example_body("floorplan", _ROOT)
    assert "/floorplan/plan-scale=1000" in body
    assert r"\draw[floorplan scale bar]" not in body
    assert r"\draw[floorplan north arrow]" not in body
    assert r"\tikzset{floorplan scale bar}" in body
    assert r"\tikzset{floorplan north arrow}" in body


def test_example_bodies_are_not_preambles():
    for template_id in TEMPLATE_IDS:
        body = example_body(template_id, _ROOT)
        assert body.strip()
        for marker in (
            "\\documentclass",
            "\\usepackage",
            "\\RequirePackage",
            "\\begin{document}",
        ):
            assert marker not in body


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_each_template_compiles_with_a_sample_body(template_id, tmp_path):
    """XeLaTeX builds preamble plus body. Markdown samples use a plain sentence.

    The image has xeCJK. A host without that package still compiles the
    kind packages; the preamble file itself keeps the font lines.
    """
    sample = example_body(template_id, _ROOT)
    if template_id == "document-shell":
        sample = "Hello from the document shell."
    tex = compose(template_id, "InstruMeasure", sample, _ROOT)
    assert re.search(r"\\documentclass(?:\[[^\]]*\])?\{article\}", tex)
    assert "a4paper" in tex
    assert "__PAPER__" not in tex
    if template_id == "fulldoc":
        assert "\\newcommand{\\EndleafLane}" not in tex
    else:
        assert "\\newcommand{\\EndleafLane}{InstruMeasure}" in tex
    assert sample in tex
    if shutil.which("kpsewhich"):
        found = subprocess.run(
            ["kpsewhich", "xeCJK.sty"],
            check=False,
            capture_output=True,
        )
        if found.returncode != 0:
            tex = (
                tex.replace("\\usepackage{fontspec}\n", "")
                .replace("\\usepackage{xeCJK}\n", "")
                .replace("\\setCJKmainfont{Noto Sans CJK TC}\n", "")
                .replace("\\input{endleaf-type.tex}\n", "")
            )
        else:
            gyre = subprocess.run(
                ["kpsewhich", "texgyrepagella-regular.otf"],
                check=False,
                capture_output=True,
            )
            if gyre.returncode != 0 or not gyre.stdout.strip():
                tex = tex.replace("\\input{endleaf-type.tex}\n", "")
    (tmp_path / "job.tex").write_text(tex, encoding="utf-8")
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
        cwd=tmp_path,
        check=False,
        timeout=180 if template_id == "fulldoc" else 90,
        capture_output=True,
        env=env,
    )
    log = (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")
    assert completed.returncode == 0, log[-800:]
    assert (tmp_path / "job.pdf").is_file()
