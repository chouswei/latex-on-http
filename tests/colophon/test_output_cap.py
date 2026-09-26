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


def _classify(returncode, stderr, elapsed=2):
    return classify_result(
        returncode=returncode,
        timed_out=False,
        elapsed=elapsed,
        capped=False,
        abort=False,
        stderr=stderr,
    )


def test_early_sigkill_is_the_memory_cap():
    assert _classify(137, b"", elapsed=2) == "failCapHit"
    assert _classify(-9, b"", elapsed=2) == "failCapHit"


def test_allocation_failure_is_the_memory_cap():
    samples = (
        b"xelatex: ooops, not enough memory (2147483648)\nCOLOPHON_STATUS render_error\n",
        b"fatal: memory exhausted (xmalloc of 1048576 bytes).\n",
        b"xelatex: Cannot allocate memory\n",
        b"xdvipdfmx:fatal: Out of memory - asked for 1048576 bytes\n",
        b"pandoc: Heap exhausted;\nCurrent maximum heap size is 2147483648 bytes.\n",
        b"Sorry, I ran out of memory.\n",
    )
    for stderr in samples:
        assert _classify(1, stderr) == "failCapHit"


def test_xdvipdfmx_bitmap_warning_is_not_a_cap():
    stderr = (
        b"xdvipdfmx:warning: large interlaced bitmap might cause out of memory\n"
        b"job.tex:2: Undefined control sequence.\n"
    )
    assert _classify(1, stderr) == "rejectRenderError"


def test_ordinary_tex_error_stays_a_render_error():
    assert (
        _classify(1, b"job.tex:9: Undefined control sequence.\n") == "rejectRenderError"
    )


def test_allocation_phrase_on_success_is_not_a_cap():
    assert _classify(0, b"COLOPHON_STATUS ok\nwords of memory out of 5000000\n") == "ok"


def test_wall_clock_kill_beats_an_allocation_phrase():
    assert _classify(137, b"fatal: memory exhausted\n", elapsed=60) == "failTimeout"


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
