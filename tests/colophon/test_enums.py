# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

import pytest

import colophon.enums
from colophon.enums import JobRejected, parse_job
from tests.colophon.conftest import valid_body
from tests.colophon.lanes import PLACEHOLDER_LANES, PROD_LANES

_TEMPLATES = Path(__file__).resolve().parents[2] / "colophon/share/templates"


def test_known_enums_accepted():
    job = parse_job(valid_body())
    assert job.lane == "lane-a"
    assert job.output_format == "pdf"
    assert job.template_id == "document-shell"
    assert job.input_kind == "markdown"
    assert job.source == "Hello"
    assert job.page_size == "a4"


def test_pagesize_letter_is_accepted():
    job = parse_job(valid_body(pageSize="letter"))
    assert job.page_size == "letter"


def test_pagesize_explicit_a4_is_accepted():
    job = parse_job(valid_body(pageSize="a4"))
    assert job.page_size == "a4"


@pytest.mark.parametrize("value", ["A4", "legal", "a5", "", None, 4])
def test_pagesize_invalid_is_rejected(value):
    with pytest.raises(JobRejected) as caught:
        parse_job(valid_body(pageSize=value))
    assert caught.value.reason == "pageSize"
    assert caught.value.message
    assert "\n" not in caught.value.message


def test_http_rejects_invalid_pagesize(client, auth, runner):
    response = client.post(
        "/v1/jobs",
        json=valid_body(pageSize="legal"),
        headers=auth,
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "rejectInvalidInput"
    assert body["field"] == "pageSize"
    assert body["result"] == "refused"
    assert body["message"]
    assert "\n" not in body["message"]
    assert runner.calls == []


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("lane", "instruMeasure", "lane"),
        ("lane", "Other", "lane"),
        ("lane", "", "lane"),
        ("outputFormat", "PDF", "outputFormat"),
        ("outputFormat", "odt", "outputFormat"),
        ("templateId", "latex", "templateId"),
        ("templateId", "", "templateId"),
        ("templateId", None, "templateId"),
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
                templateId="circuits",
                body="\\documentclass{article}\n\\begin{document}x\\end{document}",
            )
        )
    assert caught.value.reason == "documentclass"


def test_raw_preamble_is_rejected():
    for source in (
        "\\usepackage{geometry}\nHello.",
        "\\RequirePackage{tikz}\nHello.",
        "\\begin{document}\nHello.",
    ):
        with pytest.raises(JobRejected) as caught:
            parse_job(valid_body(templateId="circuits", body=source))
        assert caught.value.reason == "preamble"


def test_http_rejects_documentclass(client, auth, runner):
    response = client.post(
        "/v1/jobs",
        json=valid_body(
            templateId="circuits",
            body="\\documentclass{article}\nHello.",
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
            "lane": "lane-a",
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
            "lane": "lane-b",
            "outputFormat": "pdf",
            "inputKind": "tex",
            "resources": [{"main": True, "content": "Hello from TeX"}],
        },
        headers=auth,
    )
    assert response.status_code == 200
    assert response.data == b"%PDF-1.4"
    assert runner.calls[0].lane == "lane-b"
    assert runner.calls[0].input_kind == "tex"


@pytest.mark.real_lanes
def test_production_lanes_are_unpatched_and_enforced():
    # Unpatched: the list the worker ships, one template folder per lane.
    assert colophon.enums.LANES == PROD_LANES
    folders = {p.name for p in _TEMPLATES.iterdir() if p.is_dir() and p.name != "owned"}
    assert set(PROD_LANES) == folders
    assert not set(PLACEHOLDER_LANES) & set(PROD_LANES)
    for lane in PROD_LANES:
        assert parse_job(valid_body(lane=lane)).lane == lane
    for lane in PLACEHOLDER_LANES:
        with pytest.raises(JobRejected) as caught:
            parse_job(valid_body(lane=lane))
        assert caught.value.reason == "lane"


def test_unknown_lane_is_rejected_while_placeholders_are_patched_in():
    assert set(PLACEHOLDER_LANES) <= set(colophon.enums.LANES)
    for lane in ("lane-zzz", "", None, "LANE-A"):
        with pytest.raises(JobRejected) as caught:
            parse_job(valid_body(lane=lane))
        assert caught.value.reason == "lane"


def test_http_rejects_unknown_lane_while_patched(client, auth, runner):
    response = client.post("/v1/jobs", json=valid_body(lane="lane-zzz"), headers=auth)
    assert response.status_code == 400
    assert response.get_json()["field"] == "lane"
    assert runner.calls == []
