# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from colophon.enums import JobRejected, parse_job
from tests.colophon.conftest import valid_body


def test_known_enums_accepted():
    job = parse_job(valid_body())
    assert job.lane == "InstruMeasure"
    assert job.output_format == "pdf"
    assert job.input_kind == "markdown"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("lane", "instruMeasure", "lane"),
        ("lane", "Other", "lane"),
        ("lane", "", "lane"),
        ("outputFormat", "PDF", "outputFormat"),
        ("outputFormat", "odt", "outputFormat"),
        ("inputKind", "latex", "inputKind"),
        ("inputKind", "html", "inputKind"),
    ],
)
def test_unknown_enum_rejected(field, value, reason):
    with pytest.raises(JobRejected) as caught:
        parse_job(valid_body(**{field: value}))
    assert caught.value.reason == reason


def test_tex_documentclass_rejected():
    with pytest.raises(JobRejected) as caught:
        parse_job(
            valid_body(
                inputKind="tex",
                input="\\documentclass{article}\n\\begin{document}x\\end{document}",
            )
        )
    assert caught.value.reason == "documentclass"


def test_http_rejects_documentclass(client, auth, runner):
    response = client.post(
        "/v1/jobs",
        json=valid_body(
            inputKind="tex",
            input="\\documentclass{article}\nHello.",
        ),
        headers=auth,
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "rejectInvalidInput"
    assert body["field"] == "documentclass"
    assert body["result"] == "refused"
    assert runner.calls == []


def test_lualatex_compiler_is_rejected(client, auth, runner):
    response = client.post(
        "/v1/jobs",
        json=valid_body(compiler="lualatex"),
        headers=auth,
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "rejectInvalidInput"
    assert body["field"] == "compiler"
    assert runner.calls == []


def test_omitted_compiler_stays_xelatex(client, auth, runner):
    response = client.post("/v1/jobs", json=valid_body(), headers=auth)
    assert response.status_code == 200
    assert runner.calls[0].source == "Hello"


def test_http_rejects_unknown_lane(client, auth, runner):
    response = client.post("/v1/jobs", json=valid_body(lane="Public"), headers=auth)
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "rejectInvalidInput"
    assert body["field"] == "lane"
    assert runner.calls == []


def test_http_rejects_unknown_format(client, auth):
    response = client.post(
        "/v1/jobs", json=valid_body(outputFormat="svg"), headers=auth
    )
    assert response.status_code == 400
    assert response.get_json()["field"] == "outputFormat"


def test_legacy_url_resource_rejected(client, auth, runner):
    response = client.post(
        "/builds/sync",
        json={
            "compiler": "pdflatex",
            "lane": "Weft",
            "resources": [{"main": True, "url": "https://example.invalid/a.tex"}],
        },
        headers=auth,
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "rejectInvalidInput"
    assert runner.calls == []


def test_legacy_xelatex_content_is_accepted(client, auth, runner):
    response = client.post(
        "/builds/sync",
        json={
            "compiler": "xelatex",
            "lane": "Investor",
            "outputFormat": "pdf",
            "inputKind": "tex",
            "resources": [{"main": True, "content": "Hello from TeX"}],
        },
        headers=auth,
    )
    assert response.status_code == 200
    assert response.data == b"%PDF-1.4"
    assert runner.calls[0].lane == "Investor"
    assert runner.calls[0].input_kind == "tex"
