# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import subprocess
import sys

from colophon.limits import OUTPUT_CAP_BYTES
from colophon.runner import (
    Outcome,
    classify_result,
    collect_process,
    enforce_output_cap,
)
from colophon.worker import create_app
from colophon.killswitch import KillSwitch
from tests.colophon.conftest import valid_body
import pytest


def test_exact_cap_is_allowed():
    payload = b"x" * OUTPUT_CAP_BYTES
    assert enforce_output_cap(payload) == payload


def test_one_byte_over_cap_is_rejected():
    payload = b"x" * (OUTPUT_CAP_BYTES + 1)
    with pytest.raises(ValueError):
        enforce_output_cap(payload)


def test_collector_keeps_exact_cap():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'abcd')"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, _stderr, code, timed_out, capped = collect_process(
        proc, cap=4, timeout=10, kill=proc.kill
    )
    assert code == 0
    assert timed_out is False
    assert capped is False
    assert stdout == b"abcd"


def test_collector_discards_output_over_cap():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'abcdef')"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, _stderr, _code, timed_out, capped = collect_process(
        proc, cap=4, timeout=10, kill=proc.kill
    )
    assert capped is True
    assert timed_out is False
    assert stdout == b""


def test_http_over_cap_is_an_error(config, switch_path, monitor, auth):
    from colophon.runner import Supervisor

    def runner(job, name, abort_event):
        return Outcome(
            kind="ok",
            body=b"x" * (OUTPUT_CAP_BYTES + 1),
            content_type="application/pdf",
        )

    supervisor = Supervisor(runner, retry_after_sec=10)
    app = create_app(config, KillSwitch(switch_path), monitor, supervisor)
    response = app.test_client().post("/v1/jobs", json=valid_body(), headers=auth)
    assert response.status_code == 413
    assert response.get_json()["error"] == "failCapHit"
    assert response.data != b"x" * (OUTPUT_CAP_BYTES + 1)


def test_timeout_is_not_a_render_error():
    assert (
        classify_result(
            returncode=137,
            timed_out=False,
            elapsed=60,
            capped=False,
            abort=False,
            stderr=b"",
        )
        == "failTimeout"
    )
    assert (
        classify_result(
            returncode=10,
            timed_out=False,
            elapsed=2,
            capped=False,
            abort=False,
            stderr=b"COLOPHON_STATUS render_error\n",
        )
        == "rejectRenderError"
    )
