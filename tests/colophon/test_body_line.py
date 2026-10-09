# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R58-BODYLINE: a TeX error inside the caller's body names the body line.

Runs in CI or the image (make test). Not a podman integration test.
"""

from pathlib import Path

import pytest

from colophon import sandbox_render
from colophon.diagnostics import relocate_to_body
from colophon.render_plan import RenderPlanError
from colophon.templates import compose, compose_with_body_line

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"

BODY = "\\section{A}\nOne.\n\nTwo \\undefinedthing.\n"


@pytest.mark.parametrize("template_id", ["fulldoc", "document-shell", "sysml"])
@pytest.mark.parametrize("page_size,orientation", [("a4", None), ("a3", "landscape")])
def test_body_start_line_points_at_the_first_body_line(template_id, page_size, orientation):
    text, start = compose_with_body_line(
        template_id, "Weft", BODY, _OWNED, page_size=page_size, orientation=orientation
    )
    lines = text.split("\n")
    assert lines[start - 1].endswith("\\section{A}")
    assert lines[start - 1 + 3] == "Two \\undefinedthing."
    assert compose(template_id, "Weft", BODY, _OWNED, page_size, orientation) == text


def test_error_inside_the_body_is_relocated():
    found = relocate_to_body({"file": "job.tex", "line": 43, "message": "x"}, 40, 5)
    assert found["file"] == "body" and found["line"] == 4


@pytest.mark.parametrize(
    "diagnostic",
    [
        {"file": "job.tex", "line": 39, "message": "preamble"},
        {"file": "job.tex", "line": 45, "message": "after the body"},
        {"file": "endleaf-page.tex", "line": 41, "message": "other file"},
        {"file": "job.tex", "line": None, "message": "no line"},
    ],
)
def test_errors_outside_the_body_keep_job_tex(diagnostic):
    before = dict(diagnostic)
    assert relocate_to_body(dict(diagnostic), 40, 5) == before


def test_relocate_tolerates_no_diagnostic_or_no_start():
    assert relocate_to_body(None, 40, 5) is None
    assert relocate_to_body({"file": "job.tex", "line": 41}, None, 5)["file"] == "job.tex"


def test_render_error_diagnostic_names_the_body_line(monkeypatch, capsys, tmp_path):
    """Whole sandbox path: compose, write job.tex, fail the TeX run, read the log.

    Every /tmp path is redirected into tmp_path, so the test never touches the host /tmp.
    """
    text, start = compose_with_body_line("fulldoc", "Weft", BODY, _OWNED)
    error_line = start + 3

    class Plan:
        files = {}
        commands = (("xelatex", "job.tex"),)
        output_path = str(tmp_path / "job.pdf")

    def boxed(path):
        # Keep every /tmp path the sandbox touches inside tmp_path.
        text_path = str(path)
        if text_path == "/tmp" or text_path.startswith("/tmp/"):
            return Path(str(tmp_path) + text_path[len("/tmp") :])
        return Path(text_path)

    def fake_run(command):
        assert (tmp_path / "job.tex").read_text(encoding="utf-8") == text
        (tmp_path / "job.log").write_text(
            f"./job.tex:{error_line}: Undefined control sequence.\n", encoding="utf-8"
        )
        raise RenderPlanError("command")

    monkeypatch.setattr(sandbox_render, "Path", boxed)

    monkeypatch.setattr(sandbox_render, "build_render_plan", lambda job: Plan())
    monkeypatch.setattr(
        sandbox_render,
        "compose_with_body_line",
        lambda *args, **kwargs: compose_with_body_line(*args[:3], _OWNED, **kwargs),
    )
    monkeypatch.setattr(sandbox_render, "_run", fake_run)
    payload = (
        '{"body": %s, "templateId": "fulldoc", "outputFormat": "pdf", "lane": "Weft"}'
        % __import__("json").dumps(BODY)
    ).encode()
    code = sandbox_render.render_to_stdout(payload)
    err = capsys.readouterr().err
    assert code != 0
    diag_line = next(line for line in err.splitlines() if line.startswith("ENDLEAF_DIAG "))
    diagnostic = __import__("json").loads(diag_line.split(" ", 1)[1])
    assert diagnostic["file"] == "body"
    assert diagnostic["line"] == 4
    assert not (tmp_path / "job.tex").exists()
