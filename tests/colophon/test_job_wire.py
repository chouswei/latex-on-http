# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R56-WIRE and ENDLEAF-R56-CONTRACT.

Live 2026-10-08: the HTTP worker parsed pageSize letter, then the runner
rebuilt the sandbox stdin from four keys and dropped it, so every PDF was
A4. The #14 tests called parse_job and compose directly and never crossed
the runner. These tests post the gate's exact body to POST /v1/jobs and
follow it through the real runner into the sandbox render.
"""

import dataclasses
import io
import json
import shutil
import sys
import types
from pathlib import Path

import pytest

import colophon.podman_args as podman_args
import colophon.runner as runner_mod
from colophon.enums import ORIENTATIONS, PAGE_SIZES, parse_job, job_payload
from colophon.killswitch import KillSwitch
from colophon.runner import Supervisor, make_podman_runner
from colophon.sandbox_render import render_to_stdout
from colophon.templates import TEMPLATES, example_body
from colophon.worker import create_app
from tests.colophon.conftest import TOKEN
from tests.colophon.test_page_size import _mediabox_pt

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"
_CONTRACT = json.loads(
    (_ROOT / "tests/colophon/fixtures/contract/worker-job-contract.json").read_text(
        encoding="utf-8"
    )
)
# Portrait width x height in pt. Landscape swaps them.
_SIZES = {"a4": (595.28, 841.89), "letter": (612.0, 792.0), "a3": (841.89, 1190.55)}


def _jobs():
    for template_id, asset in TEMPLATES.items():
        formats = ("pdf",) if template_id == "fulldoc" else ("pdf", "html", "docx")
        for output_format in formats:
            for size in PAGE_SIZES:
                for orientation in (None,) + ORIENTATIONS:
                    payload = {
                        "body": "Hello",
                        "templateId": template_id,
                        "outputFormat": output_format,
                        "lane": "Weft",
                        "pageSize": size,
                    }
                    if orientation is not None:
                        payload["orientation"] = orientation
                    yield payload


def test_job_payload_round_trips_every_field():
    """A JobSpec field the runner forgets fails here, whatever its name."""
    names = {field.name for field in dataclasses.fields(parse_job(next(_jobs())))}
    assert {"page_size", "orientation"} <= names
    for payload in _jobs():
        job = parse_job(payload)
        wire = json.loads(json.dumps(job_payload(job)))
        assert parse_job(wire) == job, payload


@pytest.mark.parametrize("value", ["A3", "legal", "", 4])
def test_page_size_message_names_three_sizes(value):
    from colophon.enums import JobRejected

    with pytest.raises(JobRejected) as caught:
        parse_job({**next(_jobs()), "pageSize": value})
    assert caught.value.message == "pageSize must be a4, letter or a3"


@pytest.mark.parametrize("value", ["Landscape", "wide", "", 1])
def test_orientation_message_is_one_line(value):
    from colophon.enums import JobRejected

    with pytest.raises(JobRejected) as caught:
        parse_job({**next(_jobs()), "orientation": value})
    assert caught.value.reason == "orientation"
    assert caught.value.message == "orientation must be portrait or landscape"


class _InProcessSandbox:
    """Stands in for ``podman run``: stdin goes to the real sandbox render."""

    def __init__(self, sent):
        self._sent = sent
        self.returncode = None
        outer = self

        class _Stdin:
            def write(self, data):
                outer._sent.append(data)

            def close(self):
                outer._run()

        self.stdin = _Stdin()
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(b"")

    def _run(self):
        out, err = _Capture(), _Capture()
        saved = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            self.returncode = render_to_stdout(self._sent[-1])
        finally:
            sys.stdout, sys.stderr = saved
        self.stdout = io.BytesIO(out.buffer.getvalue())
        self.stderr = io.BytesIO(err.text.encode("utf-8"))

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        return None


class _Capture:
    def __init__(self):
        self.buffer = io.BytesIO()
        self._text = []

    def write(self, data):
        if isinstance(data, bytes):
            self.buffer.write(data)
        else:
            self._text.append(data)
        return len(data)

    def flush(self):
        return None

    @property
    def text(self):
        return "".join(self._text)


@pytest.fixture
def wired(monkeypatch, tmp_path, config, switch_path, monitor):
    """Worker HTTP app over the real podman runner; podman runs in-process."""
    from tests.colophon.test_fulldoc import _bind_tex

    _bind_tex(monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(runner_mod, "probe_podman_version", lambda _podman: (4, 4, 0))
    monkeypatch.setattr(runner_mod, "_podman_rm", lambda *_a: None)
    monkeypatch.setattr(runner_mod, "_podman_kill", lambda *_a: None)
    monkeypatch.setattr(
        podman_args, "require_cpu_controller", lambda *_a, **_k: ("cpu", "memory", "pids")
    )
    # Only the runner's podman spawn is replaced; TeX still uses subprocess.
    fake = types.SimpleNamespace(**vars(runner_mod.subprocess))
    fake.Popen = lambda *_a, **_k: _InProcessSandbox(sent)
    monkeypatch.setattr(runner_mod, "subprocess", fake)
    switch = KillSwitch(switch_path)
    supervisor = Supervisor(make_podman_runner(config, switch), retry_after_sec=10)
    app = create_app(config, switch, monitor, supervisor)
    app.config["TESTING"] = True
    return app.test_client(), sent


def _gate_body(case, template_id="circuits"):
    body = dict(_CONTRACT["base"])
    body.pop("pageSize")
    body.update(case)
    body["templateId"] = template_id
    body["body"] = example_body(template_id, _OWNED)
    return body


def _expected(case):
    width, height = _SIZES[case.get("pageSize", "a4")]
    if case.get("orientation") == "landscape":
        width, height = height, width
    return width, height


def test_contract_fixture_has_all_six_combinations():
    pairs = {
        (case["pageSize"], case["orientation"])
        for case in _CONTRACT["cases"]
        if "pageSize" in case and "orientation" in case
    }
    assert pairs == {(s, o) for s in PAGE_SIZES for o in ORIENTATIONS}


@pytest.mark.parametrize("case", _CONTRACT["cases"], ids=lambda c: json.dumps(c))
def test_gate_body_reaches_the_sandbox_unchanged(case, wired):
    client, sent = wired
    body = _gate_body(case)
    http_job = parse_job(body)
    client.post("/v1/jobs", json=body, headers={"Authorization": f"Bearer {TOKEN}"})
    assert len(sent) == 1
    sandbox_job = parse_job(json.loads(sent[0]))
    assert sandbox_job == http_job
    assert sandbox_job.page_size == case.get("pageSize", "a4")
    assert sandbox_job.orientation == case.get("orientation")


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
@pytest.mark.parametrize("case", _CONTRACT["cases"], ids=lambda c: json.dumps(c))
def test_gate_body_gives_the_asked_pdf_page(case, wired):
    """End to end: gate body -> HTTP -> runner -> sandbox -> XeLaTeX -> MediaBox."""
    client, _sent = wired
    response = client.post(
        "/v1/jobs",
        json=_gate_body(case),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)[-1500:]
    assert response.headers["X-Endleaf-Result"] == "ok"
    width, height = _mediabox_pt(response.get_data())
    expected = _expected(case)
    assert width == pytest.approx(expected[0], abs=0.05)
    assert height == pytest.approx(expected[1], abs=0.05)


# ENDLEAF-R56-FIT. sysml keeps its own landscape choice when orientation
# is omitted, on every size; a named orientation is kept or refused.
_WIDE = (_ROOT / "tests/colophon/fixtures/review/wide-175.tex")


def _sysml(tmp_path, page_size, orientation, halt=True):
    from tests.colophon.test_fulldoc import _TEXINPUTS, _type_ready

    from colophon.templates import compose

    tex = compose(
        "sysml", "Weft", _WIDE.read_text(encoding="utf-8"), _OWNED,
        page_size=page_size, orientation=orientation,
    )
    if not _type_ready():
        tex = tex.replace("\\input{endleaf-type.tex}\n", "")
    (tmp_path / "wide.tex").write_text(tex, encoding="utf-8")
    env = dict(__import__("os").environ)
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    completed = __import__("subprocess").run(
        ["xelatex", "-no-shell-escape", "-interaction=nonstopmode",
         "-halt-on-error", "-file-line-error", "wide.tex"],
        cwd=tmp_path, check=False, timeout=180, capture_output=True, env=env,
    )
    log = (tmp_path / "wide.log").read_text(encoding="utf-8", errors="replace")
    return completed.returncode, log, tmp_path / "wide.pdf"


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
@pytest.mark.parametrize(
    "page_size,orientation",
    [("a4", None), ("letter", None), ("a4", "landscape"), ("a3", "landscape")],
)
def test_wide_sysml_is_landscape_on_each_size(tmp_path, page_size, orientation):
    from tests.colophon.test_fulldoc import _fit

    code, log, pdf = _sysml(tmp_path, page_size, orientation)
    assert code == 0, log[-2000:]
    assert _fit(log)["page"] == "landscape"
    width, height = _mediabox_pt(pdf.read_bytes())
    expected = _SIZES[page_size]
    assert width == pytest.approx(expected[1], abs=0.05)
    assert height == pytest.approx(expected[0], abs=0.05)


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_wide_sysml_named_portrait_is_refused_not_turned(tmp_path):
    from tests.colophon.test_fulldoc import _unwrap

    code, log, pdf = _sysml(tmp_path, "a4", "portrait")
    assert code != 0
    text = _unwrap(log)
    assert "picture does not fit portrait A4 at the declared type size" in text
    assert "Omit orientation to let Endleaf choose" in text
    assert not pdf.is_file()


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_wide_sysml_fits_a3_portrait_when_orientation_is_omitted(tmp_path):
    """A3 portrait gives the text block the extra width, so 175 mm fits."""
    from tests.colophon.test_fulldoc import _fit

    code, log, pdf = _sysml(tmp_path, "a3", None)
    assert code == 0, log[-2000:]
    assert _fit(log)["page"] == "portrait"
    width, height = _mediabox_pt(pdf.read_bytes())
    assert width == pytest.approx(_SIZES["a3"][0], abs=0.05)
    assert height == pytest.approx(_SIZES["a3"][1], abs=0.05)


# document-shell and the six named kinds take the Pandoc lane path.
def _lane_header(lane, variables):
    """Pandoc's substitution for the four page lines of a lane template."""
    import re

    lines = (_ROOT / f"colophon/share/templates/{lane}/pandoc.latex").read_text(
        encoding="utf-8"
    ).splitlines()[:4]
    out = []
    for line in lines:
        def _if(match):
            return match.group(2) if variables.get(match.group(1)) else ""

        line = re.sub(r"\$if\((\w+)\)\$(.*?)\$endif\$", _if, line)
        line = re.sub(r"\$(\w+)\$", lambda m: variables.get(m.group(1), ""), line)
        out.append(line)
    return "\n".join(out) + "\n"


def _pandoc_vars(command):
    found = {}
    for flag, value in zip(command, command[1:]):
        if flag == "-V":
            key, _, val = value.partition("=")
            found[key] = val
    return found


@pytest.mark.parametrize("case", _CONTRACT["cases"], ids=lambda c: json.dumps(c))
def test_pandoc_lane_gets_size_and_orientation(case, tmp_path):
    from colophon.render_plan import build_render_plan

    job = parse_job(
        {**_gate_body(case, "document-shell"), "body": "Hello", "lane": "Weft"}
    )
    found = _pandoc_vars(build_render_plan(job).commands[0])
    size = case.get("pageSize", "a4")
    assert found["papersize"] == ("a4" if size == "a3" else size)
    assert found["endleafpaper"] == {"a4": "A4", "letter": "Letter", "a3": "A3"}[size]
    assert found.get("endleaforientation") == case.get("orientation")
    if shutil.which("xelatex") is None:
        return
    import os
    import subprocess

    tex = _lane_header("Weft", found) + "\\begin{document}\nHello.\n\\end{document}\n"
    (tmp_path / "lane.tex").write_text(tex, encoding="utf-8")
    env = dict(os.environ)
    env["TEXINPUTS"] = (
        str(_ROOT / "colophon/share/tex/latex/colophon-v1") + os.pathsep
        + env.get("TEXINPUTS", "")
    )
    done = subprocess.run(
        ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "lane.tex"],
        cwd=tmp_path, check=False, timeout=90, capture_output=True, env=env,
    )
    assert done.returncode == 0, done.stdout[-1500:]
    width, height = _mediabox_pt((tmp_path / "lane.pdf").read_bytes())
    expected = _expected(case)
    assert width == pytest.approx(expected[0], abs=0.05)
    assert height == pytest.approx(expected[1], abs=0.05)
