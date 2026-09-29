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
_FIT = re.compile(
    r"ENDLEAF_FIT shipped=([0-9.]+)pt line=([0-9.]+)pt "
    r"high=([0-9.]+)pt avail=([0-9.]+)pt "
    r"uniform=([0-9.]+) unit=([0-9.]+) type=([0-9.]+)"
)
_BOX = re.compile(
    r"SYSMLBOX\s+(\S+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)"
)
_WORD = re.compile(
    r'<word xMin="([0-9.]+)" yMin="([0-9.]+)" xMax="([0-9.]+)" yMax="([0-9.]+)">(.*?)</word>'
)
_PAGE = re.compile(r'<page width="([0-9.]+)" height="([0-9.]+)">')
_FIT_TEX = _ROOT / "colophon/share/tex/latex/colophon-v1/endleaf-fit.tex"


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


def _unwrap(log):
    """Join TeX log lines. A line of 79 columns or more is a hard wrap."""
    pieces = []
    pending = ""
    for line in log.splitlines():
        pending = pending + line if pending else line
        if len(line) < 79:
            pieces.append(pending)
            pending = ""
    if pending:
        pieces.append(pending)
    return "\n".join(pieces)


def _fit(log):
    found = _FIT.search(_unwrap(log))
    assert found, _unwrap(log)[-2000:]
    shipped, line, high, avail, uniform, unit, type_size = (
        float(item) for item in found.groups()
    )
    return {
        "shipped": shipped,
        "line": line,
        "high": high,
        "avail": avail,
        "uniform": uniform,
        "unit": unit,
        "type": type_size,
        "type_text": found.group(7),
    }


def _shipped_boxes(log):
    text = _unwrap(log)
    start = text.rfind("ENDLEAF_FIT_SHIP")
    assert start >= 0, text[-1500:]
    end = text.find("\nENDLEAF_FIT ", start)
    assert end > start, text[start : start + 1500]
    boxes = []
    for kind, x0, y0, x1, y1 in _BOX.findall(text[start:end]):
        xa, xb = sorted((float(x0), float(x1)))
        ya, yb = sorted((float(y0), float(y1)))
        boxes.append((kind, xa, ya, xb, yb))
    return boxes


def _overlap(a0, a1, b0, b1):
    return min(a1, b1) - max(a0, b0)


def _crosses_outline(label, outline, tol=0.4):
    """A hit on both axes that is not strictly inside the outline."""
    ox = _overlap(label[1], label[3], outline[1], outline[3])
    oy = _overlap(label[2], label[4], outline[2], outline[4])
    if ox <= tol or oy <= tol:
        return False
    inside = (
        label[1] >= outline[1] - 0.05
        and label[3] <= outline[3] + 0.05
        and label[2] >= outline[2] - 0.05
        and label[4] <= outline[4] + 0.05
    )
    return not inside


def _bbox_words(pdf, page):
    extracted = subprocess.run(
        ["pdftotext", "-bbox", "-f", str(page), "-l", str(page), str(pdf), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert extracted.returncode == 0, extracted.stderr
    page_box = _PAGE.search(extracted.stdout)
    assert page_box, extracted.stdout[:500]
    words = [
        {
            "xMin": float(x0),
            "yMin": float(y0),
            "xMax": float(x1),
            "yMax": float(y1),
            "text": word,
        }
        for x0, y0, x1, y1, word in _WORD.findall(extracted.stdout)
    ]
    return float(page_box.group(1)), float(page_box.group(2)), words


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
    fit = _fit(log)
    assert fit["type"] >= 7
    assert fit["shipped"] <= fit["line"] + 0.2
    assert fit["high"] <= fit["avail"] + 0.2
    assert re.search(rf"type\s+{re.escape(fit['type_text'])}\s*pt", text)
    assert pages >= 2
    _assert_float_page_stacks_at_the_top(pdf)
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


def _assert_float_page_stacks_at_the_top(pdf):
    """Figure 2 and Figure 3 share the top of page 2, with a fixed gap."""
    _width, height, words = _bbox_words(pdf, 2)
    captions = []
    for index, word in enumerate(words):
        if word["text"] != "Figure" or index + 1 >= len(words):
            continue
        number = words[index + 1]["text"].rstrip(":")
        if number in {"2", "3"}:
            captions.append(word["yMin"])
    assert captions == sorted(captions)
    assert len(captions) >= 2, [word["text"] for word in words]
    assert captions[0] < 220
    assert max(captions) < height * 0.45
    assert captions[-1] - captions[0] < 180


def _assert_labels_clear_outlines(boxes):
    labels = [box for box in boxes if box[0] in {"text", "plab"}]
    outlines = [box for box in boxes if box[0] == "part"]
    lines = [box for box in boxes if box[0] == "line"]
    assert labels and outlines, boxes
    for label in labels:
        for outline in outlines:
            assert not _crosses_outline(label, outline), (label, outline)
        for line in lines:
            assert (
                _overlap(label[1], label[3], line[1], line[3]) <= 0.4
                or _overlap(label[2], label[4], line[2], line[4]) <= 0.4
            ), (label, line)


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_wide_sysml_canvas_fits_the_line(tmp_path):
    body = "\\makeatletter\\sysml@marktracetrue\\makeatother\n" + (
        _REVIEW / "wide-175.tex"
    ).read_text(encoding="utf-8")
    tex = compose("sysml", "Weft", body, _OWNED)
    pdf, log = _xelatex(tmp_path, "wide.tex", tex)
    assert "Overfull \\hbox" not in log
    assert "Overfull \\vbox" not in log
    fit = _fit(log)
    assert fit["shipped"] <= fit["line"] + 0.2
    assert fit["high"] <= fit["avail"] + 0.2
    assert fit["uniform"] == pytest.approx(0.7, abs=0.01)
    assert fit["unit"] > 0.9
    assert fit["type"] == pytest.approx(7, abs=0.05)
    assert fit["type_text"] == "7"
    assert _pages(pdf) == 1
    text = _text(pdf)
    assert "參數" in text
    assert re.search(r"type\s+7\s*pt", text)
    assert "type 10" not in text
    _assert_labels_clear_outlines(_shipped_boxes(log))


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_sysml_header_and_canvas_stay_together(tmp_path):
    body = (_REVIEW / "tall-split.tex").read_text(encoding="utf-8")
    tex = compose("sysml", "Weft", body, _OWNED)
    pdf, log = _xelatex(tmp_path, "tall.tex", tex)
    assert "Overfull \\vbox" not in log
    assert "Overfull \\hbox" not in log
    assert _pages(pdf) == 1
    fit = _fit(log)
    assert fit["high"] <= fit["avail"] + 0.2
    assert fit["uniform"] < 1
    assert fit["unit"] == pytest.approx(1, abs=0.001)
    assert fit["type"] >= 7
    text = _text(pdf)
    assert "View" in text
    assert "幫浦" in text
    assert "末端" in text
    assert re.search(rf"type\s+{re.escape(fit['type_text'])}\s*pt", text)


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_hash_in_a_float_body_compiles(tmp_path):
    body = (_REVIEW / "hash-float.tex").read_text(encoding="utf-8")
    tex = compose("fulldoc", "Weft", body, _OWNED)
    pdf, _log = _xelatex(tmp_path, "hash.tex", tex)
    assert _pages(pdf) == 1
    text = _text(pdf)
    assert "#" in text
    assert "0" in text and "2" in text


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_plain_pictures_are_not_fitted(tmp_path):
    body = (
        "\\begin{tikzpicture}\n"
        "\\draw (0,0) -- (15,0);\n"
        "\\end{tikzpicture}\n"
        "\\begin{circuitikz}\n"
        "\\draw (0,0) to[R] (15,0);\n"
        "\\end{circuitikz}\n"
    )
    tex = compose("fulldoc", "Weft", body, _OWNED)
    _pdf, log = _xelatex(tmp_path, "widepic.tex", tex)
    unwrapped = _unwrap(log)
    warnings = re.findall(
        r"ENDLEAF_WIDE_PICTURE width=([0-9.]+)pt line=([0-9.]+)pt", unwrapped
    )
    assert len(warnings) == 2, unwrapped[-2000:]
    for width, line in warnings:
        assert float(width) > float(line)
    assert "ENDLEAF_FIT " not in unwrapped


def test_float_bodies_are_not_collected():
    fit = _FIT_TEX.read_text(encoding="utf-8")
    assert "\\def\\figure" in fit
    assert "\\def\\table" in fit
    assert "\\elfit@figopt" in fit
    assert "\\RenewDocumentEnvironment{figure}" not in fit
    assert "\\RenewDocumentEnvironment{table}" not in fit
    assert "\\resizebox" not in fit
    assert "ENDLEAF_WIDE_PICTURE" in fit


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


def _assert_refs_resolved(text):
    """Captions number on the first pass. ``??`` is an unresolved \\ref."""
    assert "??" not in text
    assert re.search(r"Figure\s+1", text)
    assert re.search(r"Figure\s+2", text)
    assert re.search(r"Figure\s+3", text)
    assert re.search(r"Table\s+1", text)
    assert re.search(r"圖\s*1", text), text
    assert re.search(r"表\s*1", text), text
    assert re.search(r"Section\s+1", text), text


@pytest.mark.skipif(
    shutil.which("xelatex") is None
    or shutil.which("pdftotext") is None
    or shutil.which("pdfinfo") is None,
    reason="xelatex, pdftotext, or pdfinfo is not installed",
)
def test_fulldoc_cross_references_resolve(tmp_path, monkeypatch):
    _bind_tex(monkeypatch, tmp_path)
    body = (_KINDS / "fulldoc.tex").read_text(encoding="utf-8")
    code, pdf, err = _render(
        valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=body),
        monkeypatch,
    )
    assert code == 0, err[-2000:]
    assert pdf.startswith(b"%PDF")
    assert "ENDLEAF_STATUS ok" in err
    assert "ENDLEAF_OVERFULL 0" in err
    path = tmp_path / "fulldoc-refs.pdf"
    path.write_bytes(pdf)
    assert 1 <= _pages(path) <= 16
    _assert_refs_resolved(_text(path))
