# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import json

from colophon.enums import JobSpec
from colophon.notation import degrade_inline_notation, notation_warnings
from colophon.render_plan import build_render_plan
from tests.colophon.conftest import valid_body

_MESSAGE = (
    "Inline siunitx and mhchem notation is PDF only. "
    "HTML and DOCX keep the source text."
)
_PROSE = "Water is \\qty{2}{\\metre} and \\ce{H2O}."


def _warning(source, output_format, input_kind="markdown"):
    found = notation_warnings(source, input_kind, output_format)
    assert len(found) == 1
    return found[0]


def test_html_keeps_inline_notation_as_source_text():
    degraded = degrade_inline_notation(_PROSE, "markdown", "html")
    assert degraded == "Water is `\\qty{2}{\\metre}` and `\\ce{H2O}`."
    warning = _warning(_PROSE, "html")
    assert warning == {
        "code": "notationPdfOnly",
        "packages": ["mhchem", "siunitx"],
        "message": _MESSAGE,
    }
    plan = build_render_plan(
        JobSpec(
            source=_PROSE,
            input_kind="markdown",
            output_format="html",
            lane="Weft",
        )
    )
    assert plan.files["/tmp/input.md"] == degraded


def test_docx_keeps_inline_notation_as_source_text():
    degraded = degrade_inline_notation(_PROSE, "tex", "docx")
    assert degraded == ("Water is \\verb|\\qty{2}{\\metre}| and \\verb|\\ce{H2O}|.")
    warning = _warning(_PROSE, "docx", input_kind="tex")
    assert warning["code"] == "notationPdfOnly"
    assert warning["packages"] == ["mhchem", "siunitx"]
    assert warning["message"] == _MESSAGE
    plan = build_render_plan(
        JobSpec(
            source=_PROSE,
            input_kind="tex",
            output_format="docx",
            lane="Weft",
        )
    )
    assert plan.files["/tmp/input.tex"] == degraded


def test_pdf_still_typesets_inline_notation():
    assert degrade_inline_notation(_PROSE, "markdown", "pdf") == _PROSE
    assert notation_warnings(_PROSE, "markdown", "pdf") == []
    plan = build_render_plan(
        JobSpec(
            source=_PROSE,
            input_kind="markdown",
            output_format="pdf",
            lane="Weft",
        )
    )
    assert plan.files["/tmp/input.md"] == _PROSE


def test_fenced_diagram_is_not_rewritten():
    source = "```tikz\n\\ce{H2O}\n```\n\nWater is \\ce{H2O}.\n"
    degraded = degrade_inline_notation(source, "markdown", "html")
    assert degraded.startswith("```tikz\n\\ce{H2O}\n```\n")
    assert "Water is `\\ce{H2O}`." in degraded
    assert notation_warnings("```tikz\n\\ce{H2O}\n```\n", "markdown", "html") == []
    assert notation_warnings("\\chemfig{H-O-H}", "tex", "docx") == []
    assert notation_warnings("\\usepackage{siunitx}", "tex", "html") == []


def _posted(client, auth, runner, output_format):
    response = client.post(
        "/v1/jobs",
        json=valid_body(body=_PROSE, outputFormat=output_format),
        headers=auth,
    )
    assert response.status_code == 200
    assert response.data == b"%PDF-1.4"
    assert response.headers["X-Endleaf-Result"] == "ok"
    assert runner.calls[0].source == _PROSE
    record = json.loads(response.headers["X-Endleaf-Job"])
    assert record["result"] == "ok"
    assert record["warnings"] == [
        {
            "code": "notationPdfOnly",
            "packages": ["mhchem", "siunitx"],
            "message": _MESSAGE,
        }
    ]
    return record


def test_html_job_returns_a_notation_warning(client, auth, runner):
    _posted(client, auth, runner, "html")


def test_docx_job_returns_a_notation_warning(client, auth, runner):
    _posted(client, auth, runner, "docx")
