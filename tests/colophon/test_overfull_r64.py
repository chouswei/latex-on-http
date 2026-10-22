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
from colophon.overfull import MAX_ROWS, body_tables, column_shares, overfull_rows, parse_colspec

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
        "Overfull \\hbox (12.25pt too wide) in paragraph at lines 5--5\n[]x\n[1\n\n]\n"
        "Overfull \\vbox (17.3pt too high) detected at line 8\n[2]\n"
        "Overfull \\hbox (12.25pt too wide) in alignment at lines 6--6\n[3]\n"
        "Overfull \\vbox (3.0pt too high) has occurred while \\output is active []\n"
        "Overfull \\hbox (99.0pt too wide) in paragraph at lines 1--1\n"  # preamble, not body
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
    log = "Overfull \\hbox (4.0pt too wide) in paragraph at lines 6--7\n[1]\n"
    mapping = layout_map(log, body_start=5, body_lines=4)
    assert mapping == {"v": 1, "overfullTotal": 1, "overfull": [{"line": 2, "pt": 4.0, "axis": "h", "page": 1}]}
    assert layout_map("clean log [1]", body_start=5, body_lines=4) is None


def test_caps_keep_total_and_max_rows_fits_the_header():
    lines = "".join(f"Overfull \\hbox ({i}.5pt too wide) in paragraph at lines {i + 5}--{i + 5}\n[{i}]\n" for i in range(1, 101))
    rows, total = overfull_rows(lines, body_start=5, body_lines=200)
    assert total == 100 and len(rows) == MAX_ROWS
    assert [row["pt"] for row in rows] == sorted((row["pt"] for row in rows), reverse=True)
    # maxRows measurement: MAX_ROWS worst-case rows (12-column table field, 5-digit lines,
    # random pt) must encode to under a third of the map cap.
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
                "table": {"firstLine": rng.randint(10000, 99999), "n": 12, "share": [round(rng.random(), 4) for _ in range(12)], "rules": 13},
            }
            for _ in range(MAX_ROWS)
        ],
    }
    encoded = encode_map(worst)
    assert encoded is not None and len(encoded) < LAYOUT_MAP_CAP_BYTES // 3, len(encoded)
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
