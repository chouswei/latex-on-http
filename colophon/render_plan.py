# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Commands that run inside the sandbox. Shell-escape stays off."""

import re
from dataclasses import dataclass

from colophon.enums import JobSpec
from colophon.limits import SHARE_ROOT
from colophon.notation import degrade_inline_notation


class RenderPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderPlan:
    files: dict
    commands: tuple
    output_path: str


def _template(lane, name):
    return f"{SHARE_ROOT}/templates/{lane}/{name}"


# Image PATH lists /usr/local/bin first. The name is absolute so a job
# cannot select another binary. The sandbox runs this with cwd /tmp.
XELATEX_BIN = "/usr/local/bin/xelatex-nonescape"

# \ref and \pageref read the aux file. One XeLaTeX run writes it and
# leaves ?? in the PDF. A control word such as \refstepcounter does not
# match: the next character after \ref must not be a letter.
_AUX_REF = re.compile(r"\\(?:page)?ref(?![A-Za-z])")


def xelatex_argv(tex_name):
    """XeLaTeX with shell-escape forced off. The wrapper repeats the flag.

    ``tex_name`` is a relative file in the job directory. ``openin_any=p``
    refuses an absolute path and ``..``. Aux files are written beside that
    name, so ``openout_any`` stays ``p`` as well.
    """
    if (
        not tex_name
        or tex_name.startswith("/")
        or tex_name.startswith("~")
        or ".." in tex_name.split("/")
    ):
        raise RenderPlanError("tex path")
    return [
        XELATEX_BIN,
        "-no-shell-escape",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-cnf-line=openin_any=p",
        "-cnf-line=openout_any=p",
        tex_name,
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


def source_needs_aux_pass(source):
    """True when a TeX body contains ``\\ref`` or ``\\pageref``.

    The sandbox writes ``job.aux`` beside ``job.tex``. A second identical
    XeLaTeX command reads that file. Bodies without those commands stay
    one pass so the wall-clock cap is unchanged for them.
    """
    return bool(source) and _AUX_REF.search(source) is not None


def build_render_plan(job: JobSpec) -> RenderPlan:
    if not isinstance(job, JobSpec):
        raise RenderPlanError("job")
    files = {}
    if job.input_kind == "tex" and job.output_format == "pdf":
        wrapper = _template(job.lane, "wrapper.tex")
        # The sandbox reads the wrapper from the image and substitutes the body.
        files["/tmp/body.tex"] = job.source
        files["/tmp/job.tex"] = None  # filled by the sandbox from the wrapper
        passes = (xelatex_argv("job.tex"),)
        if source_needs_aux_pass(job.source):
            passes = passes + (xelatex_argv("job.tex"),)
        return RenderPlan(
            files=files,
            commands=passes,
            output_path="/tmp/job.pdf",
        )
    source_name = "/tmp/input.md" if job.input_kind == "markdown" else "/tmp/input.tex"
    # Fenced diagrams stay on the diagram filter (images). Inline
    # siunitx and mhchem stay as source text for HTML and DOCX.
    files[source_name] = degrade_inline_notation(
        job.source, job.input_kind, job.output_format
    )
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
            # Pandoc writes an absolute input.tex. xelatex-nonescape turns
            # that into a basename before TeX reads it. openin stays p.
            "--pdf-engine-opt=-cnf-line=openin_any=p",
            "--pdf-engine-opt=-cnf-line=openout_any=p",
            "--template",
            _template(job.lane, "pandoc.latex"),
            "-V",
            f"papersize={job.page_size}",
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
