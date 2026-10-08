# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

from colophon.enums import JobSpec
from colophon.limits import SHARE_ROOT
from colophon.render_plan import build_render_plan, source_needs_aux_pass

_ROOT = Path(__file__).resolve().parents[2]


def _job(
    lane="InstruMeasure", output_format="pdf", input_kind="markdown", source="Hello"
):
    return JobSpec(
        source=source,
        input_kind=input_kind,
        output_format=output_format,
        lane=lane,
    )


def _flat(plan):
    return " ".join(" ".join(command) for command in plan.commands)


def test_pandoc_pdf_always_passes_papersize():
    plan = build_render_plan(_job())
    command = plan.commands[0]
    assert "-V" in command
    assert "papersize=a4" in command
    letter = build_render_plan(
        JobSpec(
            source="Hello",
            input_kind="markdown",
            output_format="pdf",
            lane="Weft",
            page_size="letter",
        )
    )
    assert "papersize=letter" in letter.commands[0]


def test_xelatex_shell_escape_is_off():
    plan = build_render_plan(_job())
    flat = _flat(plan)
    assert "-no-shell-escape" in flat
    assert "-cnf-line=openout_any=a" not in flat
    assert "-cnf-line=openout_any=p" in flat
    assert "-cnf-line=openin_any=p" in flat
    assert "--pdf-engine xelatex" in flat
    assert "/usr/local/bin/xelatex-nonescape" not in flat
    assert "-shell-escape" not in flat.replace("-no-shell-escape", "")
    assert "--shell-escape" not in flat


def test_each_lane_uses_its_own_template():
    seen = set()
    for lane in ("InstruMeasure", "Weft", "Investor"):
        plan = build_render_plan(_job(lane=lane))
        templates = [
            part
            for command in plan.commands
            for part in command
            if part.startswith(f"{SHARE_ROOT}/templates/")
        ]
        assert templates
        assert all(f"/{lane}/" in part for part in templates)
        seen.add(tuple(templates))
    assert len(seen) == 3


def test_html_embeds_diagrams_in_the_single_response():
    plan = build_render_plan(_job(output_format="html"))
    flat = _flat(plan)
    assert "--embed-resources" in flat
    assert "--standalone" in flat


def test_html_and_docx_render_fenced_diagrams_as_images():
    for output_format in ("html", "docx"):
        flat = _flat(build_render_plan(_job(output_format=output_format)))
        assert "diagram.lua" in flat
        assert "--pdf-engine" not in flat


def test_tex_pdf_uses_xelatex_not_pandoc():
    plan = build_render_plan(_job(input_kind="tex"))
    assert len(plan.commands) == 1
    flat = _flat(plan)
    assert flat.startswith("/usr/local/bin/xelatex-nonescape ")
    assert flat.endswith(" job.tex")
    assert "/tmp/job.tex" not in flat
    assert "-output-directory" not in flat
    assert "pandoc" not in flat
    assert "-no-shell-escape" in flat
    assert "-cnf-line=openout_any=a" not in flat
    assert "-cnf-line=openout_any=p" in flat
    assert "-cnf-line=openin_any=p" in flat


def test_ref_and_pageref_schedule_a_second_identical_pass():
    body = (_ROOT / "tests/colophon/fixtures/kinds/fulldoc.tex").read_text(
        encoding="utf-8"
    )
    assert source_needs_aux_pass(body)
    assert source_needs_aux_pass("See \\ref{sec:layout} and \\pageref{sec:layout}.")
    assert source_needs_aux_pass("\\ref*{fig:sysml}")
    assert not source_needs_aux_pass("Hello")
    assert not source_needs_aux_pass("\\refstepcounter{section}")
    assert not source_needs_aux_pass("\\renewcommand{\\foo}{bar}")
    plan = build_render_plan(_job(input_kind="tex", lane="Weft", source=body))
    assert len(plan.commands) == 2
    assert plan.commands[0] == plan.commands[1]
    assert plan.commands[0][-1] == "job.tex"
    flat = _flat(plan)
    assert flat.count(" job.tex") == 2
    assert "-no-shell-escape" in flat
    assert "-shell-escape" not in flat.replace("-no-shell-escape", "")
    assert "--shell-escape" not in flat
    plain = build_render_plan(_job(input_kind="tex", source="Page."))
    assert len(plain.commands) == 1
