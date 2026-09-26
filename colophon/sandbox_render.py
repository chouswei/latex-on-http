# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-container render. Stdout is the artifact; nothing is kept afterwards."""

import json
import os
import subprocess
import sys
from pathlib import Path

from colophon.diagnostics import first_tex_error
from colophon.enums import JobRejected, parse_job
from colophon.limits import OUTPUT_CAP_BYTES, SHARE_ROOT
from colophon.render_plan import RenderPlanError, build_render_plan


def _status(name):
    sys.stderr.write(f"COLOPHON_STATUS {name}\n")
    sys.stderr.flush()


def _read_int(paths):
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        token = text.strip().split()
        if token and token[0].isdigit():
            return int(token[0])
    return None


def _memory_mode():
    """``cgroup`` when the launcher applied ``--memory``, else ``rlimit``.

    The launcher sets ``COLOPHON_MEMORY_MODE``. A direct sandbox run falls
    back to the container's own controller list.
    """
    raw = os.environ.get("COLOPHON_MEMORY_MODE", "").strip()
    if raw in ("cgroup", "rlimit"):
        return raw
    try:
        text = Path("/sys/fs/cgroup/cgroup.controllers").read_text(encoding="utf-8")
    except OSError:
        return "rlimit"
    if "memory" in text.split():
        return "cgroup"
    return "rlimit"


def _emit_meters():
    payload = {
        "memoryPeak": _read_int(
            (
                "/sys/fs/cgroup/memory.peak",
                "/sys/fs/cgroup/memory/memory.max_usage_in_bytes",
            )
        ),
        "pidsPeak": _read_int(("/sys/fs/cgroup/pids.peak",)),
        "memoryMode": _memory_mode(),
    }
    sys.stderr.write(
        "COLOPHON_METERS " + json.dumps(payload, separators=(",", ":")) + "\n"
    )
    sys.stderr.flush()


def _emit_diag(diagnostic):
    if not diagnostic:
        return
    sys.stderr.write(
        "COLOPHON_DIAG " + json.dumps(diagnostic, separators=(",", ":")) + "\n"
    )
    sys.stderr.flush()


def _collect_logs():
    chunks = []
    for path in sorted(Path("/tmp").glob("*.log")):
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


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
    plan = None
    data = b""
    status = "invalid"
    diagnostic = None
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
        job = parse_job(payload)
        plan = build_render_plan(job)
    except (UnicodeError, json.JSONDecodeError, JobRejected, RenderPlanError):
        status = "invalid"
    else:
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
            status = "cap" if len(data) > OUTPUT_CAP_BYTES else "ok"
        except (OSError, RenderPlanError):
            diagnostic = first_tex_error(_collect_logs())
            status = "render_error"
        finally:
            paths = list(plan.files) + [plan.output_path, "/tmp/job.tex"]
            for pattern in ("*.log", "*.aux", "*.out", "*.toc", "*.xdv"):
                paths.extend(str(path) for path in Path("/tmp").glob(pattern))
            for path in paths:
                try:
                    Path(path).unlink()
                except OSError:
                    pass
    _emit_meters()
    if status == "render_error":
        _emit_diag(diagnostic)
    _status(status)
    if status == "ok":
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        return 0
    if status == "cap":
        return 11
    if status == "render_error":
        return 10
    return 12


def main():
    raw = sys.stdin.buffer.read()
    code = render_to_stdout(raw)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
