# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Commands that run inside the sandbox. Shell-escape stays off."""

from dataclasses import dataclass

from colophon.enums import JobSpec
from colophon.limits import SHARE_ROOT


class RenderPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderPlan:
    files: dict
    commands: tuple
    output_path: str


def _template(lane, name):
    return f"{SHARE_ROOT}/templates/{lane}/{name}"


def xelatex_argv(tex_path):
    """XeLaTeX with shell-escape forced off. The wrapper repeats the flag."""
    return [
        "/usr/local/bin/xelatex-nonescape",
        "-no-shell-escape",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        # Debian sets openout_any=p, which refuses the aux file when the
        # job path is absolute. The read-only root still confines writes
        # to the /tmp tmpfs.
        "-cnf-line=openout_any=a",
        "-output-directory=/tmp",
        tex_path,
    ]


def _pandoc_base(source_path, job):
    return [
        "pandoc",
        source_path,
        "--from",
        "markdown" if job.input_kind == "markdown" else "latex",
        "--lua-filter",
        f"{SHARE_ROOT}/lock-diagram.lua",
        "--lua-filter",
        f"{SHARE_ROOT}/diagram.lua",
    ]


def build_render_plan(job: JobSpec) -> RenderPlan:
    if not isinstance(job, JobSpec):
        raise RenderPlanError("job")
    files = {}
    if job.input_kind == "tex" and job.output_format == "pdf":
        wrapper = _template(job.lane, "wrapper.tex")
        # The sandbox reads the wrapper from the image and substitutes the body.
        files["/tmp/body.tex"] = job.source
        files["/tmp/job.tex"] = None  # filled by the sandbox from the wrapper
        return RenderPlan(
            files=files,
            commands=(xelatex_argv("/tmp/job.tex"),),
            output_path="/tmp/job.pdf",
        )
    source_name = "/tmp/input.md" if job.input_kind == "markdown" else "/tmp/input.tex"
    files[source_name] = job.source
    command = _pandoc_base(source_name, job)
    if job.output_format == "pdf":
        output = "/tmp/out.pdf"
        # Pandoc 3 accepts only a known engine name here, not a path.
        # /usr/local/bin/xelatex is the no-shell-escape wrapper, and that
        # directory is first on PATH in the image.
        command += [
            "--pdf-engine",
            "xelatex",
            "--pdf-engine-opt=-no-shell-escape",
            "--pdf-engine-opt=-interaction=nonstopmode",
            "--pdf-engine-opt=-halt-on-error",
            "--pdf-engine-opt=-file-line-error",
            "--pdf-engine-opt=-cnf-line=openout_any=a",
            "--template",
            _template(job.lane, "pandoc.latex"),
            "-o",
            output,
        ]
    elif job.output_format == "html":
        output = "/tmp/out.html"
        command += [
            "--standalone",
            "--embed-resources",
            "--template",
            _template(job.lane, "pandoc.html"),
            "-o",
            output,
        ]
    else:
        output = "/tmp/out.docx"
        command += [
            "--reference-doc",
            _template(job.lane, "reference.docx"),
            "-o",
            output,
        ]
    return RenderPlan(files=files, commands=(tuple(command),), output_path=output)
