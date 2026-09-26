# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import json

from colophon.diagnostics import first_tex_error, parse_stderr
from colophon.job_result import job_record, result_class
from colophon.runner import Outcome
from colophon.sandbox_render import render_to_stdout
from colophon.worker import create_app
from tests.colophon.conftest import valid_body


def test_result_class_names():
    assert result_class("ok") == "ok"
    assert result_class("failTimeout") == "failTimeout"
    assert result_class("failCapHit") == "failCapHit"
    assert result_class("rejectRenderError") == "renderError"
    for kind in (
        "rejectInvalidInput",
        "rejectBusy",
        "rejectLoadShed",
        "rejectKillSwitch",
        "rejectSpawnFail",
    ):
        assert result_class(kind) == "refused"


def test_first_tex_error_skips_warnings():
    log = "job.tex:2: Warning: something\njob.tex:9: Undefined control sequence.\n"
    found = first_tex_error(log)
    assert found["file"] == "job.tex"
    assert found["line"] == 9
    assert found["engine"] == "tex"
    assert "Undefined" in found["message"]


def test_parse_stderr_exposes_a_reported_memory_mode():
    stderr = b'COLOPHON_METERS {"memoryPeak":100,"pidsPeak":7,"memoryMode":"rlimit"}\n'
    meters, diagnostic = parse_stderr(stderr)
    assert diagnostic is None
    assert meters["memoryMode"] == "rlimit"
    record = job_record("ok", 0.4, 100, 7, memory_mode=meters["memoryMode"])
    assert record["memory"] == {"peak": 100, "mode": "rlimit"}


def test_unknown_memory_mode_is_left_out():
    stderr = b'COLOPHON_METERS {"memoryPeak":1,"pidsPeak":2,"memoryMode":"swap"}\n'
    meters, _diagnostic = parse_stderr(stderr)
    assert "memoryMode" not in meters
    assert "mode" not in job_record("ok", 0.1, 1, 2, memory_mode="swap")["memory"]


def test_parse_stderr_reads_meters_and_the_first_diagnostic():
    stderr = (
        b'COLOPHON_DIAG {"engine":"tikz","message":"fail at line 4","file":null,"line":null,"fence":0}\n'
        b'COLOPHON_METERS {"memoryPeak":100,"pidsPeak":7}\n'
        b"COLOPHON_DIAG {not the first}\n"
    )
    meters, diagnostic = parse_stderr(stderr)
    assert meters == {"memoryPeak": 100, "pidsPeak": 7}
    assert diagnostic["engine"] == "tikz"
    assert diagnostic["fence"] == 0
    assert diagnostic["line"] == 4


def test_invalid_render_emits_meters(capsys, monkeypatch):
    monkeypatch.setenv("COLOPHON_MEMORY_MODE", "rlimit")
    assert render_to_stdout(b"not-json") == 12
    err = capsys.readouterr().err
    assert "COLOPHON_METERS " in err
    assert '"memoryMode":"rlimit"' in err
    assert "COLOPHON_STATUS invalid" in err


def test_refused_job_json_has_null_peaks(client, auth):
    response = client.post(
        "/v1/jobs",
        json=valid_body(templateId="nope"),
        headers=auth,
    )
    body = response.get_json()
    assert body["error"] == "rejectInvalidInput"
    assert body["result"] == "refused"
    assert body["wallSec"] is None
    assert body["memory"]["peak"] is None
    assert body["pids"]["peak"] is None
    assert "diagnostic" not in body


def test_render_error_json_includes_the_diagnostic(config, switch_path, monitor, auth):
    from colophon.killswitch import KillSwitch
    from colophon.runner import Supervisor

    diagnostic = {
        "engine": "tikz",
        "message": "boom at line 2",
        "file": "tikz-image.tex",
        "line": 2,
        "fence": 0,
    }
    outcome = Outcome(
        kind="rejectRenderError",
        wall_sec=1.25,
        memory_peak=4096,
        pids_peak=12,
        diagnostic=diagnostic,
    )

    class _Runner:
        def __call__(self, job, name, abort_event):
            return outcome

    app = create_app(
        config, KillSwitch(switch_path), monitor, Supervisor(_Runner(), 10)
    )
    response = app.test_client().post("/v1/jobs", json=valid_body(), headers=auth)
    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "rejectRenderError"
    assert body["result"] == "renderError"
    assert body["wallSec"] == 1.25
    assert body["memory"]["peak"] == 4096
    assert body["pids"]["peak"] == 12
    assert body["diagnostic"] == diagnostic


def test_success_keeps_the_artifact_and_puts_meters_in_a_header(
    config, switch_path, monitor, auth
):
    from colophon.killswitch import KillSwitch
    from colophon.runner import Supervisor

    outcome = Outcome(
        kind="ok",
        body=b"%PDF-1.4",
        content_type="application/pdf",
        wall_sec=0.5,
        memory_peak=100,
        pids_peak=3,
    )

    class _Runner:
        def __call__(self, job, name, abort_event):
            return outcome

    app = create_app(
        config, KillSwitch(switch_path), monitor, Supervisor(_Runner(), 10)
    )
    response = app.test_client().post("/v1/jobs", json=valid_body(), headers=auth)
    assert response.status_code == 200
    assert response.data == b"%PDF-1.4"
    assert response.headers["X-Colophon-Result"] == "ok"
    record = json.loads(response.headers["X-Colophon-Job"])
    assert record == job_record("ok", 0.5, 100, 3)


def test_success_header_exposes_the_memory_mode(config, switch_path, monitor, auth):
    from colophon.killswitch import KillSwitch
    from colophon.runner import Supervisor

    outcome = Outcome(
        kind="ok",
        body=b"%PDF-1.4",
        content_type="application/pdf",
        wall_sec=0.5,
        memory_peak=100,
        pids_peak=3,
        memory_mode="cgroup",
    )

    class _Runner:
        def __call__(self, job, name, abort_event):
            return outcome

    app = create_app(
        config, KillSwitch(switch_path), monitor, Supervisor(_Runner(), 10)
    )
    response = app.test_client().post("/v1/jobs", json=valid_body(), headers=auth)
    record = json.loads(response.headers["X-Colophon-Job"])
    assert record["memory"] == {"peak": 100, "mode": "cgroup"}
