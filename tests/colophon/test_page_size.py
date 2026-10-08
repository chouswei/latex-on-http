# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional job pageSize. Default A4; letter is the other accepted value."""

import re
import shutil
import subprocess
import zlib
from pathlib import Path

import pytest

from colophon.enums import parse_job
from colophon.templates import compose, example_body
from tests.colophon.conftest import valid_body

_ROOT = (
    Path(__file__).resolve().parents[2] / "colophon" / "share" / "templates" / "owned"
)
_SHARE = Path(__file__).resolve().parents[2] / "colophon" / "share" / "templates"
_PREAMBLE = (
    Path(__file__).resolve().parents[2]
    / "colophon/share/tex/latex/colophon-v1/colophon-v1-preamble.tex"
)
_MEDIA = re.compile(
    rb"/MediaBox\s*\[\s*([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*\]"
)
_A4 = (595.28, 841.89)
_LETTER = (612.0, 792.0)


def _inflate_pdf(data):
    """XeLaTeX often zlib-compresses the page dict. Stdlib only; no pypdf."""
    chunks = [data]
    for raw in re.findall(rb"stream\r?\n(.+?)\r?\nendstream", data, flags=re.DOTALL):
        try:
            chunks.append(zlib.decompress(raw))
        except zlib.error:
            continue
    return b"\n".join(chunks)


def _mediabox_pt(data):
    found = _MEDIA.search(_inflate_pdf(data))
    assert found is not None, data[:400]
    x0, y0, x1, y1 = (float(part) for part in found.groups())
    return (x1 - x0, y1 - y0)


def _paper_probe(tex):
    """Keep the composed class options. XeLaTeX needs the kernel page dims."""
    found = re.search(r"\\documentclass(?:\[[^\]]*\])?\{article\}", tex)
    assert found is not None, tex[:200]
    assert "\\input{colophon-v1-preamble.tex}" in tex
    return (
        found.group(0)
        + "\n\\ifdefined\\pdfpagewidth"
        + "\n  \\pdfpagewidth=\\paperwidth"
        + "\n  \\pdfpageheight=\\paperheight"
        + "\n\\fi"
        + "\n\\begin{document}\nHello.\n\\end{document}\n"
    )


def _compile(tmp_path, tex):
    tex = _paper_probe(tex)
    (tmp_path / "job.tex").write_text(tex, encoding="utf-8")
    completed = subprocess.run(
        [
            "xelatex",
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "job.tex",
        ],
        cwd=tmp_path,
        check=False,
        timeout=90,
        capture_output=True,
    )
    log = (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")
    assert completed.returncode == 0, log[-800:]
    pdf = tmp_path / "job.pdf"
    assert pdf.is_file()
    return pdf.read_bytes()


def _body(template_id):
    if template_id == "document-shell":
        return "Hello from the document shell."
    return example_body(template_id, _ROOT)


def test_compose_replaces_paper_placeholder():
    shared = _PREAMBLE.read_text(encoding="utf-8")
    assert "\\pdfpagewidth=\\paperwidth" in shared
    assert "\\pdfpageheight=\\paperheight" in shared
    a4 = compose("circuits", "Weft", "x", _ROOT)
    assert "\\documentclass[a4paper]{article}" in a4
    letter = compose("circuits", "Weft", "x", _ROOT, page_size="letter")
    assert "\\documentclass[letterpaper]{article}" in letter
    shell = compose("document-shell", "Weft", "Hello", _ROOT)
    assert "\\documentclass[10pt,a4paper]{article}" in shell
    full = compose("fulldoc", "Weft", "Hello", _ROOT, page_size="letter")
    assert "\\documentclass[10pt,letterpaper]{article}" in full


def test_lane_pandoc_templates_use_papersize_variable():
    for lane in ("Weft", "InstruMeasure", "Investor"):
        text = (_SHARE / lane / "pandoc.latex").read_text(encoding="utf-8")
        assert text.splitlines()[0] == r"\documentclass[10pt,$papersize$paper]{article}"


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
@pytest.mark.parametrize("template_id", ("document-shell", "circuits"))
@pytest.mark.parametrize(
    "page_size,expected",
    [(None, _A4), ("letter", _LETTER)],
)
def test_job_pdf_page_size(tmp_path, template_id, page_size, expected):
    payload = valid_body(templateId=template_id, body=_body(template_id))
    if page_size is not None:
        payload["pageSize"] = page_size
    job = parse_job(payload)
    if page_size is None:
        assert job.page_size == "a4"
    else:
        assert job.page_size == page_size
    tex = compose(job.template_id, job.lane, job.source, _ROOT, page_size=job.page_size)
    work = tmp_path / f"{template_id}-{job.page_size}"
    work.mkdir()
    width, height = _mediabox_pt(_compile(work, tex))
    assert width == pytest.approx(expected[0], abs=0.05)
    assert height == pytest.approx(expected[1], abs=0.05)
