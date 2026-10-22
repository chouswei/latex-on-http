# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R64-ROWS and the worker side of ENDLEAF-R64-VERIFY."""

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.layout_map import LAYOUT_MAP_CAP_BYTES, decode_map, encode_map, layout_map
from colophon.overfull import MAX_ROWS, MAX_TABLE_COLUMNS, body_tables, column_shares, overfull_rows, parse_colspec

_NEEDS_PDFTEX = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is not installed")

_PREAMBLE = "\\documentclass{article}\n\\usepackage[a4paper]{geometry}\n\\usepackage{longtable}\n\\begin{document}\n"
_BODY_START = 5  # job.tex line of the body's first line


def _compile(tmp_path, body):
    tex = tmp_path / "job.tex"
    tex.write_text(_PREAMBLE + body + "\n\\end{document}\n", encoding="utf-8")
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "job.tex"],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")


_TABLE = (
    "Intro paragraph.\n\n"
    "\\begin{tabular}{|p{6cm}|p{6cm}|p{5cm}|}\n\\hline\n"
    "The ingestion service that reads sensor frames & Validates every frame against the schema & Retries three times \\\\\n"
    "\\hline\n\\end{tabular}\n"
)


def test_colspec_and_shares():
    assert parse_colspec("|p{6cm}|p{6cm}|p{5cm}|") == (["6cm", "6cm", "5cm"], 4)
    assert parse_colspec("*{3}{p{2cm}}") == (["2cm"] * 3, 0)
    assert parse_colspec("@{}l>{\\raggedright}p{0.3\\linewidth}@{}") == ([None, "0.3\\linewidth"], 0)
    assert parse_colspec("Q{weird}") is None
    assert column_shares(["6cm", "6cm", "5cm"]) == [0.3529, 0.3529, 0.2941]
    assert column_shares(["60mm", "6cm"]) == [0.5, 0.5]
    assert column_shares([None, "2cm"]) == [None, None]
    assert column_shares(["0.3\\linewidth", "2cm"]) == [None, None]
    assert body_tables(_TABLE) == [(3, 7, 3, [0.3529, 0.3529, 0.2941], 4)]


def test_rows_from_synthetic_log_order_page_and_fallback():
    log = (
        "Overfull \\hbox (12.25pt too wide) in paragraph at lines 5--5\n[]x\n\n[1\n]\n"
        "Overfull \\vbox (17.3pt too high) detected at line 8\n\n[2]\n"
        "Overfull \\hbox (12.25pt too wide) in alignment at lines 6--6\n[]\n\n[3]\n"
        "Overfull \\vbox (3.0pt too high) has occurred while \\output is active []\n\n"
        "Overfull \\hbox (99.0pt too wide) in paragraph at lines 1--1\n\n"  # preamble, not body
        "Overfull \\hbox (1.0pt too wide) detected at line 9\n"  # no shipout after it
    )
    rows, total = overfull_rows(log, body_start=5, body_lines=10)
    assert total == 5  # four in the body plus one TeX gave no line for
    assert rows == [
        {"line": 4, "pt": 17.3, "axis": "v", "page": 2},
        {"line": 1, "pt": 12.25, "axis": "h", "page": 1},
        {"line": 2, "pt": 12.25, "axis": "h", "page": 3},
        {"line": 5, "pt": 1.0, "axis": "h"},
    ]
    assert overfull_rows("", body_start=5, body_lines=3) == ([], 0)
    assert overfull_rows(log, body_start=None, body_lines=3) == ([], 0)


def test_template_without_marks_sends_rows_only():
    log = "Overfull \\hbox (4.0pt too wide) in paragraph at lines 6--7\n[]\n\n[1]\n"
    mapping = layout_map(log, body_start=5, body_lines=4)
    assert mapping == {"v": 1, "overfullTotal": 1, "overfull": [{"line": 2, "pt": 4.0, "axis": "h", "page": 1}]}
    assert layout_map("clean log [1]", body_start=5, body_lines=4) is None


def test_bracketed_text_in_a_box_dump_is_not_a_page():
    # The dump after a warning holds page text; "[7]" in it is not a shipout.
    log = (
        "Overfull \\hbox (4.0pt too wide) in paragraph at lines 6--6\n"
        "[]\\OT1/cmr/m/n/10 see [7] and [8 more\n\n"
        "Underfull \\hbox (badness 10000) in paragraph at lines 7--7\n[]\\OT1/cmr/m/n/10 [9]\n\n"
        " [1] [2]\n"
    )
    rows, total = overfull_rows(log, body_start=5, body_lines=4)
    assert total == 1 and rows == [{"line": 2, "pt": 4.0, "axis": "h", "page": 1}]


def test_wide_table_row_drops_its_table_field_only():
    cols = MAX_TABLE_COLUMNS + 1
    source = "x\n\\begin{tabular}{" + "p{1cm}" * cols + "}\na\\\\\n\\end{tabular}\n"
    log = "Overfull \\hbox (9.0pt too wide) in alignment at lines 7--8\n[]\n\n[1]\n"
    rows, total = overfull_rows(log, body_start=5, body_lines=5, source=source)
    assert total == 1 and rows == [{"line": 3, "pt": 9.0, "axis": "h", "page": 1}]
    source = "x\n\\begin{tabular}{" + "p{1cm}" * MAX_TABLE_COLUMNS + "}\na\\\\\n\\end{tabular}\n"
    rows, _ = overfull_rows(log, body_start=5, body_lines=5, source=source)
    assert rows[0]["table"]["n"] == MAX_TABLE_COLUMNS


def test_over_the_cap_drops_to_total():
    rows = [{"line": i + 1, "pt": 1.5, "axis": "h", "page": 1} for i in range(4000)]
    encoded = encode_map({"v": 1, "overfullTotal": 4000, "overfull": rows}, cap=2000)
    assert decode_map(encoded) == {"v": 1, "overfullTotal": 4000}


def test_caps_keep_total_and_max_rows_fits_the_header():
    lines = "".join(f"Overfull \\hbox ({i}.5pt too wide) in paragraph at lines {i + 5}--{i + 5}\n[{i}]\n" for i in range(1, 101))
    rows, total = overfull_rows(lines, body_start=5, body_lines=200)
    assert total == 100 and len(rows) == MAX_ROWS
    assert [row["pt"] for row in rows] == sorted((row["pt"] for row in rows), reverse=True)
    # maxRows measurement: MAX_ROWS worst-case rows (MAX_TABLE_COLUMNS-column table field,
    # 5-digit lines, random pt) must encode to under half of the map cap (5224 bytes).
    rng = random.Random(64)
    worst = {
        "v": 1,
        "overfullTotal": 99999,
        "overfull": [
            {
                "line": rng.randint(10000, 99999),
                "pt": round(rng.uniform(0.1, 999.0), 5),
                "axis": rng.choice("hv"),
                "page": rng.randint(100, 999),
                "table": {"firstLine": rng.randint(10000, 99999), "n": MAX_TABLE_COLUMNS, "share": [round(rng.random(), 4) for _ in range(MAX_TABLE_COLUMNS)], "rules": MAX_TABLE_COLUMNS + 1},
            }
            for _ in range(MAX_ROWS)
        ],
    }
    encoded = encode_map(worst)
    assert encoded is not None and len(encoded) < LAYOUT_MAP_CAP_BYTES // 2, len(encoded)
    assert len(encoded) == 5224
    assert decode_map(encoded) == worst


@_NEEDS_PDFTEX
def test_issue_101_table_row_from_a_real_log(tmp_path):
    log = _compile(tmp_path, _TABLE)
    rows, total = overfull_rows(log, body_start=_BODY_START, body_lines=len(_TABLE.split("\n")), source=_TABLE)
    assert total == 1
    (row,) = rows
    assert row["axis"] == "h" and row["page"] == 1 and row["pt"] > 50
    assert row["table"] == {"firstLine": 3, "n": 3, "share": [0.3529, 0.3529, 0.2941], "rules": 4}


@_NEEDS_PDFTEX
def test_multi_page_hbox_and_vbox_map_to_their_pages(tmp_path):
    body = (
        "First page.\n\n\\noindent\\hbox to 10pt{a wide box of text}\n\n"
        "\\newpage Second page.\n\\newpage Third page.\n\n"
        "\\vbox to 5pt{\\hrule height 20pt}\n"
    )
    log = _compile(tmp_path, body)
    rows, total = overfull_rows(log, body_start=_BODY_START, body_lines=len(body.split("\n")), source=body)
    assert total == 2
    by_axis = {row["axis"]: row for row in rows}
    assert by_axis["h"]["line"] == 3 and by_axis["h"]["page"] == 1
    assert by_axis["v"]["line"] == 8 and by_axis["v"]["page"] == 3


def test_no_log_or_document_text_leaves_the_sandbox():
    marker = "ZQXMARKER"
    log = f"Overfull \\hbox (4.0pt too wide) in paragraph at lines 6--6\n[]\\OT1/cmr {marker}\n[1]\n"
    source = f"x\n\\begin{{tabular}}{{p{{6cm}}}}{marker}\\end{{tabular}}\n"
    mapping = layout_map(log, body_start=5, body_lines=4, source=source)
    assert marker not in json.dumps(mapping)
    assert marker not in decode_map(encode_map(mapping)).__repr__()


def test_clean_body_sends_nothing():
    assert overfull_rows("Underfull \\hbox (badness 10000) [1]", body_start=5, body_lines=3) == ([], 0)


# -- ENDLEAF-R64-VERIFY in the real template wrappers (render_to_stdout, xelatex) --------------------------
from colophon.layout_map import LAYOUT_MAP_PREFIX  # noqa: E402
from colophon.templates import TEMPLATES  # noqa: E402
from tests.colophon.conftest import valid_body  # noqa: E402
from tests.colophon.test_fulldoc import _bind_tex, _render, _type_ready  # noqa: E402

_NEEDS_XELATEX = pytest.mark.skipif(
    shutil.which("xelatex") is None or not _type_ready(), reason="xelatex or the type stack is not installed"
)
_TEX_TEMPLATES = sorted(t for t, asset in TEMPLATES.items() if asset.kind == "tex")
_WIDE = "\\noindent\\hbox to 10pt{a wide box of text}"
_MULTI = (
    "First page.\n\n" + _WIDE + "\n\n"
    "\\newpage Second page.\n\\newpage Third page.\n\n"
    "\\vbox to 5pt{\\hrule height 20pt}\n"
)


def _layout(err):
    for line in err.splitlines():
        if line.startswith(LAYOUT_MAP_PREFIX):
            return decode_map(line[len(LAYOUT_MAP_PREFIX):])
    return None


@_NEEDS_XELATEX
@pytest.mark.parametrize("template_id", _TEX_TEMPLATES)
def test_case1_every_tex_template_row_in_its_wrapper(template_id, tmp_path, monkeypatch):
    _bind_tex(monkeypatch, tmp_path)
    body = "Intro.\n\n" + _WIDE + "\n"
    code, pdf, err = _render(valid_body(templateId=template_id, outputFormat="pdf", body=body), monkeypatch)
    assert code == 0 and pdf.startswith(b"%PDF"), err[-1500:]
    mapping = _layout(err)
    assert mapping is not None and mapping["overfullTotal"] == 1, err[-1500:]
    (row,) = mapping["overfull"]
    assert row["line"] == 3 and row["axis"] == "h" and row["page"] == 1 and row["pt"] > 0


@_NEEDS_XELATEX
@pytest.mark.parametrize("template_id", ["fulldoc", "tikzcd"])
def test_case2_multi_page_in_the_real_wrapper(template_id, tmp_path, monkeypatch):
    _bind_tex(monkeypatch, tmp_path)
    code, _pdf, err = _render(valid_body(templateId=template_id, outputFormat="pdf", body=_MULTI), monkeypatch)
    assert code == 0, err[-1500:]
    mapping = _layout(err)
    assert mapping["overfullTotal"] == 2
    by_axis = {row["axis"]: row for row in mapping["overfull"]}
    assert by_axis["h"]["line"] == 3 and by_axis["h"]["page"] == 1
    assert by_axis["v"]["line"] == 8 and by_axis["v"]["page"] == 3


_FIX_BODY = (
    "Intro paragraph.\n\n"
    "\\noindent\\begin{tabular}{|p{\\dimexpr(\\linewidth-6\\tabcolsep-4\\arrayrulewidth)*352/1000\\relax}"
    "|p{\\dimexpr(\\linewidth-6\\tabcolsep-4\\arrayrulewidth)*352/1000\\relax}"
    "|p{\\dimexpr(\\linewidth-6\\tabcolsep-4\\arrayrulewidth)*294/1000\\relax}|}\n\\hline\n"
    "The ingestion service that reads sensor frames & Validates every frame against the schema & Retries three times \\\\\n"
    "\\hline\n\\end{tabular}\n"
)


@_NEEDS_XELATEX
@pytest.mark.parametrize("template_id", ["fulldoc", "plots"])
def test_case6_fix_string_fits_in_the_real_wrapper(template_id, tmp_path, monkeypatch):
    _bind_tex(monkeypatch, tmp_path)
    # The repro overflows in this wrapper; the Fix string (gate ENDLEAF-R64-TABLEFIT) does not.
    code, _pdf, err = _render(valid_body(templateId=template_id, outputFormat="pdf", body=_TABLE), monkeypatch)
    assert code == 0, err[-1500:]
    before = _layout(err)
    assert before["overfullTotal"] >= 1
    assert before["overfull"][0]["table"] == {"firstLine": 3, "n": 3, "share": [0.3529, 0.3529, 0.2941], "rules": 4}
    code, _pdf, err = _render(valid_body(templateId=template_id, outputFormat="pdf", body=_FIX_BODY), monkeypatch)
    assert code == 0, err[-1500:]
    after = _layout(err)
    assert after is None or not after.get("overfullTotal"), after


@_NEEDS_XELATEX
def test_case8_marker_absent_from_every_stderr_line_but_the_pdf(tmp_path, monkeypatch):
    _bind_tex(monkeypatch, tmp_path)
    marker = "ZQXMARKERQZ"
    body = "\\noindent\\hbox to 10pt{" + marker + " wide}\n\n\\begin{tabular}{p{9cm}p{9cm}}" + marker + " & b\\\\\\end{tabular}\n"
    for template_id in ("fulldoc", "circuits"):
        code, _pdf, err = _render(valid_body(templateId=template_id, outputFormat="pdf", body=body), monkeypatch)
        assert code == 0, err[-1500:]
        mapping = _layout(err)
        assert mapping["overfullTotal"] >= 1
        assert marker not in err
        assert marker not in json.dumps(mapping)


@_NEEDS_XELATEX
def test_case9_clean_body_sends_no_map_rows(tmp_path, monkeypatch):
    _bind_tex(monkeypatch, tmp_path)
    code, _pdf, err = _render(valid_body(templateId="circuits", outputFormat="pdf", body="Clean.\n"), monkeypatch)
    assert code == 0, err[-1500:]
    assert _layout(err) is None


def test_document_shell_is_not_a_tex_input_template():
    # ENDLEAF-R65 is parked: document-shell is Markdown that Pandoc compiles in its own directory, and the
    # sandbox reads the TeX log (and sends rows) only for TeX input, so it gets no rows; the gate refuses
    # strictFit there with fitUncheckable.
    assert TEMPLATES["document-shell"].kind == "markdown"
    source = Path(__file__).resolve().parents[2].joinpath("colophon/sandbox_render.py").read_text(encoding="utf-8")
    block = source[source.index("ENDLEAF-R57-WARN. Counts only"):source.index("ENDLEAF-R64-ROWS. Every TeX template")]
    assert 'job.input_kind == "tex"' in block
