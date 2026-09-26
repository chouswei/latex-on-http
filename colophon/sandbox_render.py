# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-container render. Stdout is the artifact; nothing is kept afterwards."""

import json
import subprocess
import sys
from pathlib import Path

from colophon.enums import JobRejected, parse_job
from colophon.limits import OUTPUT_CAP_BYTES, SHARE_ROOT
from colophon.render_plan import RenderPlanError, build_render_plan


def _status(name):
    sys.stderr.write(f"COLOPHON_STATUS {name}\n")
    sys.stderr.flush()


def _wrap_tex(lane, body):
    wrapper = Path(SHARE_ROOT) / "templates" / lane / "wrapper.tex"
    text = wrapper.read_text(encoding="utf-8")
    if "__BODY__" not in text:
        raise RenderPlanError("wrapper")
    return text.replace("__BODY__", body, 1)


def _run(command):
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.buffer.write(completed.stdout[-8192:])
        raise RenderPlanError("command")


def render_to_stdout(payload_bytes):
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
        job = parse_job(payload)
        plan = build_render_plan(job)
    except (UnicodeError, json.JSONDecodeError, JobRejected, RenderPlanError):
        _status("invalid")
        return 12
    try:
        for path, content in plan.files.items():
            if content is None:
                continue
            Path(path).write_text(content, encoding="utf-8")
        if job.input_kind == "tex" and job.output_format == "pdf":
            Path("/tmp/job.tex").write_text(
                _wrap_tex(job.lane, job.source), encoding="utf-8"
            )
        for command in plan.commands:
            _run(list(command))
        data = Path(plan.output_path).read_bytes()
    except (OSError, RenderPlanError):
        _status("render_error")
        return 10
    finally:
        for path in list(plan.files) + [plan.output_path, "/tmp/job.tex"]:
            try:
                Path(path).unlink()
            except OSError:
                pass
    if len(data) > OUTPUT_CAP_BYTES:
        _status("cap")
        return 11
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    _status("ok")
    return 0


def main():
    raw = sys.stdin.buffer.read()
    code = render_to_stdout(raw)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
