# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from colophon.enums import JobSpec
from colophon.limits import SHARE_ROOT
from colophon.render_plan import build_render_plan


def _job(lane="InstruMeasure", output_format="pdf", input_kind="markdown"):
    return JobSpec(
        source="Hello",
        input_kind=input_kind,
        output_format=output_format,
        lane=lane,
    )


def _flat(plan):
    return " ".join(" ".join(command) for command in plan.commands)


def test_xelatex_shell_escape_is_off():
    plan = build_render_plan(_job())
    flat = _flat(plan)
    assert "-no-shell-escape" in flat
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


def test_tex_pdf_uses_xelatex_not_pandoc():
    plan = build_render_plan(_job(input_kind="tex"))
    flat = _flat(plan)
    assert flat.startswith("/usr/local/bin/xelatex-nonescape ")
    assert "pandoc" not in flat
    assert "-no-shell-escape" in flat
