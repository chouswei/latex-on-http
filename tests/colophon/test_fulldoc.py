# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R39. fulldoc is PDF only, at most 16 pages, and wide canvases fit."""

import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from colophon.enums import JobRejected, parse_job
from colophon.limits import FULLDOC_MAX_PAGES
from colophon.pdf_pages import (
    fulldoc_page_count,
    fulldoc_page_failure,
    pages_from_log,
    pages_from_pdf,
)
from colophon.revision import package_set, package_set_hash
from colophon.sandbox_render import render_to_stdout
from colophon.templates import compose
from tests.colophon.conftest import valid_body

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"
_KINDS = _ROOT / "tests/colophon/fixtures/kinds"
_REVIEW = _ROOT / "tests/colophon/fixtures/review"
_TEXINPUTS = os.pathsep.join(
    (
        str(_ROOT / "colophon/share/tex/latex/colophon-v1"),
        str(_ROOT / "colophon/share/tex/latex/endleaf-floorplan"),
        str(_ROOT / "colophon/share/tex/latex/sysml-tikz"),
        str(_ROOT / "vendor/pidcircuittikz"),
        "",
    )
)
_PACKAGE_SET_HASH = "73d55216488d240edccd26168576fcb402ce10794e04a3ef5ee8aec2bb166b98"
_FIT = re.compile(r"ENDLEAF_FIT shipped=([0-9.]+)pt line=([0-9.]+)pt factor=([0-9.]+)")


def test_package_set_hash_is_unchanged():
    assert package_set_hash(package_set()) == _PACKAGE_SET_HASH


def test_fulldoc_html_and_docx_are_refused():
    for output_format in ("html", "docx"):
        with pytest.raises(JobRejected) as caught:
            parse_job(
                valid_body(
                    templateId="fulldoc",
                    outputFormat=output_format,
                    body="Hello.",
                )
            )
        assert caught.value.reason == "outputFormat"
    job = parse_job(valid_body(templateId="fulldoc", outputFormat="pdf", body="Hello."))
    assert job.template_id == "fulldoc"
    assert job.output_format == "pdf"
    assert job.input_kind == "tex"


def test_page_cap_message():
    assert FULLDOC_MAX_PAGES == 16
    assert fulldoc_page_failure(None) == "fulldoc page count is unreadable"
    assert fulldoc_page_failure(16) is None
    assert fulldoc_page_failure(1) is None
    assert fulldoc_page_failure(17) == "fulldoc exceeds maxPages 16 (got 17 pages)"
    assert pages_from_log("Output written on job.pdf (16 pages, 100 bytes).") == 16
    assert pages_from_log("no pages here") is None
    assert pages_from_pdf(b"%PDF-1.5\n/Type /Pages\n/Type /Page\n") == 1
    assert pages_from_pdf(b"not a pdf") is None
    assert fulldoc_page_count(b"not a pdf", "Output written on job.pdf (2 pages).") == 2


def test_sysml_preamble_keeps_the_body_in_one_minipage():
    text = (_OWNED / "sysml" / "preamble.tex").read_text(encoding="utf-8")
    assert "\\noindent\\begin{minipage}{\\linewidth}" in text
    assert text.index("\\begin{minipage}") < text.index("__BODY__")
    assert text.index("__BODY__") < text.index("\\end{minipage}")


def _xelatex(tmp_path, name, tex):
    (tmp_path / name).write_text(tex, encoding="utf-8")
    env = os.environ.copy()
    env["TEXINPUTS"] = _TEXINPUTS + env.get("TEXINPUTS", "")
    completed = subprocess.run(
        [
            "xelatex",
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            name,
        ],
        cwd=tmp_path,
        check=False,
        timeout=180,
        capture_output=True,
        env=env,
    )
    log_path = tmp_path / (Path(name).stem + ".log")
    log = (
        log_path.read_text(encoding="utf-8", errors="replace")
        if log_path.is_file()
        else completed.stdout.decode("utf-8", "replace")
    )
    assert completed.returncode == 0, log[-2000:]
    pdf = tmp_path / (Path(name).stem + ".pdf")
    assert pdf.is_file()
    return pdf, log


def _text(pdf):
    extracted = subprocess.run(
        ["pdftotext", "-raw", str(pdf), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert extracted.returncode == 0
    return extracted.stdout


def _pages(pdf):
    info = subprocess.run(
        ["pdfinfo", str(pdf)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert info.returncode == 0, info.stderr
    for line in info.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise AssertionError(info.stdout)


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_fulldoc_fixture_compiles(tmp_path):
    body = (_KINDS / "fulldoc.tex").read_text(encoding="utf-8")
    tex = compose("fulldoc", "Weft", body, _OWNED)
    pdf, log = _xelatex(tmp_path, "fulldoc.tex", tex)
    assert "Overfull \\hbox" not in log
    pages = _pages(pdf)
    assert 1 <= pages <= 16
    text = _text(pdf)
    assert "幫浦" in text
    assert "參數" in text
    assert "配置" in text
    assert "type" in text and "10" in text
    fonts = subprocess.run(
        ["pdffonts", str(pdf)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert fonts.returncode == 0, fonts.stderr
    rows = fonts.stdout.splitlines()[2:]
    assert rows
    for row in rows:
        # name and type vary in width. emb sub uni sit before the object id.
        assert row.split()[-5] == "yes", row


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_wide_sysml_canvas_fits_the_line(tmp_path):
    body = (_REVIEW / "wide-175.tex").read_text(encoding="utf-8")
    tex = compose("sysml", "Weft", body, _OWNED)
    pdf, log = _xelatex(tmp_path, "wide.tex", tex)
    assert "Overfull \\hbox" not in log
    found = _FIT.search(log)
    assert found, log[-1500:]
    shipped, line, factor = (float(item) for item in found.groups())
    assert shipped <= line + 0.2
    assert factor < 1
    assert _pages(pdf) == 1
    text = _text(pdf)
    assert "參數" in text
    assert "10" in text


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_sysml_header_and_canvas_stay_together(tmp_path):
    body = (_REVIEW / "tall-split.tex").read_text(encoding="utf-8")
    tex = compose("sysml", "Weft", body, _OWNED)
    pdf, _log = _xelatex(tmp_path, "tall.tex", tex)
    pages = _pages(pdf)
    together = False
    for number in range(1, pages + 1):
        extracted = subprocess.run(
            ["pdftotext", "-f", str(number), "-l", str(number), "-raw", str(pdf), "-"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert extracted.returncode == 0
        text = extracted.stdout
        has_header = "View" in text
        has_canvas = "幫浦" in text or "末端" in text
        if has_canvas:
            assert has_header, text
        if has_header and has_canvas:
            together = True
    assert together


def _bind_tex(monkeypatch, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    wrapper = bindir / "xelatex-nonescape"
    shutil.copy(_ROOT / "container/xelatex-nonescape", wrapper)
    wrapper.chmod(0o755)
    monkeypatch.setattr("colophon.render_plan.XELATEX_BIN", str(wrapper))
    monkeypatch.setattr("colophon.templates.SHARE_ROOT", str(_ROOT / "colophon/share"))
    monkeypatch.setenv("TEXINPUTS", _TEXINPUTS + os.environ.get("TEXINPUTS", ""))
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")


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


def _render(payload, monkeypatch):
    stdout = _Capture()
    stderr = _Capture()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    code = render_to_stdout(json.dumps(payload).encode("utf-8"))
    return code, stdout.buffer.getvalue(), stderr.text


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_fulldoc_page_cap_after_compile(tmp_path, monkeypatch):
    _bind_tex(monkeypatch, tmp_path)
    sixteen = "Page.\\newpage\n" * 15 + "Page.\n"
    code, pdf, err = _render(
        valid_body(templateId="fulldoc", outputFormat="pdf", body=sixteen),
        monkeypatch,
    )
    assert code == 0, err[-2000:]
    assert pdf.startswith(b"%PDF")
    assert "ENDLEAF_STATUS ok" in err
    seventeen = "Page.\\newpage\n" * 16 + "Page.\n"
    code, _pdf, err = _render(
        valid_body(templateId="fulldoc", outputFormat="pdf", body=seventeen),
        monkeypatch,
    )
    assert code == 11, err[-2000:]
    assert "ENDLEAF_STATUS cap" in err
    assert "fulldoc exceeds maxPages 16 (got 17 pages)" in err
    diag = json.loads(err.split("ENDLEAF_DIAG ", 1)[1].splitlines()[0])
    assert diag["message"] == "fulldoc exceeds maxPages 16 (got 17 pages)"
