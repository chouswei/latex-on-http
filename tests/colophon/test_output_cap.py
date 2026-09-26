# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import shutil
import subprocess
import sys
from pathlib import Path

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


def test_podman_255_at_timeout_is_fail_timeout():
    assert _classify(255, b"Error: timed out\n", elapsed=60.9) == "failTimeout"
    assert _classify(255, b"", elapsed=60) == "failTimeout"


def test_podman_255_early_stays_a_render_error():
    assert (
        _classify(255, b"Error: invalid argument\n", elapsed=2) == "rejectRenderError"
    )
    assert _classify(255, b"", elapsed=59.9) == "rejectRenderError"


def test_sigkill_at_the_wall_is_fail_timeout():
    assert _classify(137, b"", elapsed=60) == "failTimeout"
    assert _classify(-9, b"", elapsed=60.9) == "failTimeout"


def test_any_exit_at_the_job_timeout_is_fail_timeout():
    assert (
        _classify(1, b"job.tex:1: Undefined control sequence.\n", elapsed=60)
        == "failTimeout"
    )


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


def test_output_cap_script_breaks_the_page_every_2000_specials():
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "colophon-negative-tests.sh"
    ).read_text(encoding="utf-8")
    assert "PAGE_ITEMS = 2000" in script
    assert "\\newpage" in script


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_paged_specials_do_not_exhaust_tex_main_memory(tmp_path):
    chunk = "A" * 400
    iterations = 6000
    tex = (
        "\\documentclass{article}\n\\begin{document}\n"
        "\\special{dvipdfmx:config z 0}\n"
        "\\newcount\\i\n\\newcount\\n\n\\loop\n"
        f"\\ifnum\\i<{iterations}\n  \\advance\\i by 1\n  \\advance\\n by 1\n"
        "  \\special{pdf:literal (" + chunk + ")}\n"
        "  \\ifnum\\n=2000 \\newpage \\n=0 \\fi\n"
        "\\repeat\nDone.\n\\end{document}\n"
    )
    (tmp_path / "job.tex").write_text(tex, encoding="utf-8")
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
        timeout=60,
        capture_output=True,
    )
    log = (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")
    assert completed.returncode == 0, log[-500:]
    assert "main memory" not in log
    assert (tmp_path / "job.pdf").stat().st_size > 2 * 1024 * 1024
