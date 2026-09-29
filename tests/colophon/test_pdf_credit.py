# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R40-CREDIT. Every PDF carries Creator, Producer and Keywords."""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from colophon.revision import package_set, package_set_hash
from colophon.sandbox_render import render_to_stdout
from colophon.templates import TEMPLATE_IDS
from tests.colophon.conftest import valid_body

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"
_SHARE = _ROOT / "colophon/share"
_CREDIT_TEX = _SHARE / "tex/latex/colophon-v1/endleaf-credit.tex"
_SPECIAL = (
    r"\special{pdf:docinfo<</Creator (Endleaf by InkMirage "
    r"\string\(endleaf.inkmirage.xyz\string\)) "
    r"/Producer (Endleaf by InkMirage; XeTeX) /Keywords (Endleaf)>>}"
)
_CREATOR = "Endleaf by InkMirage (endleaf.inkmirage.xyz)"
_PRODUCER = "Endleaf by InkMirage; XeTeX"
_KEYWORDS = "Endleaf"
_PACKAGE_SET_HASH = "73d55216488d240edccd26168576fcb402ce10794e04a3ef5ee8aec2bb166b98"
_TEXINPUTS = os.pathsep.join(
    (
        str(_SHARE / "tex/latex/colophon-v1"),
        str(_SHARE / "tex/latex/endleaf-floorplan"),
        str(_SHARE / "tex/latex/sysml-tikz"),
        str(_ROOT / "vendor/pidcircuittikz"),
        "",
    )
)
_COMPILE = pytest.mark.skipif(
    shutil.which("xelatex") is None
    or shutil.which("pdfinfo") is None
    or shutil.which("pandoc") is None,
    reason="xelatex, pdfinfo, or pandoc is not installed",
)


def _runner():
    path = _ROOT / "container/run_kind_fixtures.py"
    spec = importlib.util.spec_from_file_location("endleaf_kind_fixtures", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FIXTURES = _runner()


def _fixture_paths():
    root = _ROOT / "tests/colophon/fixtures"
    kinds = sorted(
        path for path in (root / "kinds").iterdir() if path.suffix in {".tex", ".md"}
    )
    smoke = sorted((root / "smoke").glob("*.tex"))
    return kinds + smoke


def _fields(pdf_path):
    info = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert info.returncode == 0, info.stderr
    fields = {}
    for line in info.stdout.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _assert_credit(fields):
    assert fields["Creator"] == _CREATOR
    assert fields["Producer"] == _PRODUCER
    assert fields["Keywords"] == _KEYWORDS
    assert "Subject" not in fields


class _Capture:
    def __init__(self):
        self.buffer = io.BytesIO()
        self._text = []

    def write(self, data):
        if isinstance(data, bytes):
            self.buffer.write(data)
            return len(data)
        self._text.append(data)
        return len(data)

    def flush(self):
        return None

    @property
    def text(self):
        return "".join(self._text)


@pytest.fixture(scope="module")
def _diagram_lua():
    link = _SHARE / "diagram.lua"
    created = False
    if not link.exists():
        link.symlink_to(_ROOT / "vendor/diagram/diagram.lua")
        created = True
    yield
    if created:
        link.unlink()


def _bind(monkeypatch, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    wrapper = bindir / "xelatex-nonescape"
    shutil.copy(_ROOT / "container/xelatex-nonescape", wrapper)
    wrapper.chmod(0o755)
    share = str(_SHARE)
    monkeypatch.setattr("colophon.render_plan.XELATEX_BIN", str(wrapper))
    monkeypatch.setattr("colophon.render_plan.SHARE_ROOT", share)
    monkeypatch.setattr("colophon.templates.SHARE_ROOT", share)
    monkeypatch.setenv("TEXINPUTS", _TEXINPUTS + os.environ.get("TEXINPUTS", ""))
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")


def _render(payload, monkeypatch):
    stdout = _Capture()
    stderr = _Capture()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    code = render_to_stdout(json.dumps(payload).encode("utf-8"))
    return code, stdout.buffer.getvalue(), stderr.text


def test_credit_special_is_the_xetex_form():
    text = _CREDIT_TEX.read_text(encoding="utf-8")
    assert text.count(_SPECIAL) == 1
    assert "hyperref" not in text
    assert "/Subject" not in text
    assert "\\AtBeginDocument" in text
    assert package_set_hash(package_set()) == _PACKAGE_SET_HASH


def test_every_pdf_preamble_inputs_the_credit():
    shared = (_SHARE / "tex/latex/colophon-v1/colophon-v1-preamble.tex").read_text(
        encoding="utf-8"
    )
    assert "\\input{endleaf-credit.tex}" in shared
    for template_id in TEMPLATE_IDS:
        text = (_OWNED / template_id / "preamble.tex").read_text(encoding="utf-8")
        if template_id == "fulldoc":
            assert "\\input{colophon-v1-preamble.tex}" not in text
            assert "\\input{endleaf-credit.tex}" in text
            assert text.index("\\input{endleaf-credit.tex}") < text.index(
                "\\begin{document}"
            )
        else:
            assert "\\input{colophon-v1-preamble.tex}" in text
    for lane in ("InstruMeasure", "Weft", "Investor"):
        template = (_SHARE / "templates" / lane / "pandoc.latex").read_text(
            encoding="utf-8"
        )
        assert "\\input{colophon-v1-preamble.tex}" in template


@_COMPILE
def test_caller_subject_stays_and_credit_is_not_page_text(
    tmp_path, monkeypatch, _diagram_lua
):
    _bind(monkeypatch, tmp_path)
    code, pdf, err = _render(
        valid_body(
            templateId="document-shell",
            outputFormat="pdf",
            body="Hello from the document shell.",
        ),
        monkeypatch,
    )
    assert code == 0, err[-2000:]
    path = tmp_path / "hello.pdf"
    path.write_bytes(pdf)
    _assert_credit(_fields(path))
    text = subprocess.run(
        ["pdftotext", "-raw", str(path), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert text.returncode == 0
    assert "Endleaf" not in text.stdout
    assert "InkMirage" not in text.stdout
    assert "endleaf.inkmirage" not in text.stdout

    code, pdf, err = _render(
        valid_body(
            templateId="gantt",
            outputFormat="pdf",
            body="\\special{pdf:docinfo<</Subject (Band)>>}\nHello.\n",
        ),
        monkeypatch,
    )
    assert code == 0, err[-2000:]
    path.write_bytes(pdf)
    fields = _fields(path)
    assert fields["Subject"] == "Band"
    assert fields["Creator"] == _CREATOR
    assert fields["Producer"] == _PRODUCER
    assert fields["Keywords"] == _KEYWORDS


@_COMPILE
@pytest.mark.parametrize(
    "fixture",
    _fixture_paths(),
    ids=lambda path: path.name,
)
def test_fixture_pdf_has_the_document_credit(
    fixture, tmp_path, monkeypatch, _diagram_lua
):
    names = tuple(path.name for path in _fixture_paths())
    assert names == _FIXTURES.REQUIRED + _FIXTURES.SMOKE
    _bind(monkeypatch, tmp_path)
    code, pdf, err = _render(
        valid_body(
            templateId=_FIXTURES._template_id(fixture),
            outputFormat="pdf",
            lane="Weft",
            body=fixture.read_text(encoding="utf-8"),
        ),
        monkeypatch,
    )
    assert code == 0, err[-2500:]
    assert pdf.startswith(b"%PDF")
    path = tmp_path / "job.pdf"
    path.write_bytes(pdf)
    _assert_credit(_fields(path))
