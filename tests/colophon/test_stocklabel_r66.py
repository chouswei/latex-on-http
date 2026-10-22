# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R66. The stocklabel template, label page sizes, labelFit rows."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from colophon.enums import JobRejected, job_payload, parse_job
from colophon.layout_map import decode_map, label_fit_line, label_fit_map, parse_layout_map
from colophon.source_policy import reject_forbidden_source
from colophon.templates import ALLOWED_INPUTS, TEMPLATE_IDS, compose, example_body
from tests.colophon.test_page_size import _mediabox_pt

_ROOT = Path(__file__).resolve().parents[2]
_OWNED = _ROOT / "colophon/share/templates/owned"
_TEX = _ROOT / "colophon/share/tex/latex/colophon-v1"
_CONTRACT = json.loads((_ROOT / "tests/colophon/fixtures/contract/stocklabel-job.json").read_text(encoding="utf-8"))
_DK11201 = {"widthMm": 89.8, "heightMm": 29.0, "marginXMm": 2.95, "marginYMm": 1.55}
_MM = 72 / 25.4


def _payload(**extra):
    payload = {
        "body": example_body("stocklabel", _OWNED),
        "templateId": "stocklabel",
        "outputFormat": "pdf",
        "lane": "Weft",
        "labelSize": dict(_DK11201),
    }
    payload.update(extra)
    return payload


def test_stocklabel_is_a_template_with_its_own_input():
    assert "stocklabel" in TEMPLATE_IDS
    assert "endleaf-label.tex" in ALLOWED_INPUTS
    assert (_TEX / "endleaf-label.tex").is_file()


def test_parse_job_keeps_the_label_size_and_round_trips():
    job = parse_job(_payload())
    assert job.label_size == (89.8, 29.0, 2.95, 1.55)
    wire = job_payload(job)
    assert "pageSize" not in wire
    assert wire["labelSize"] == _DK11201
    assert parse_job(wire) == job


@pytest.mark.parametrize(
    "extra",
    [
        {"pageSize": "a4"},
        {"orientation": "landscape"},
        {"outputFormat": "html"},
        {"labelSize": None},
        {"labelSize": {"widthMm": 89.8, "heightMm": 29.0}},
        {"labelSize": {**_DK11201, "widthMm": 5}},
        {"labelSize": {**_DK11201, "heightMm": 400}},
        {"labelSize": {**_DK11201, "marginXMm": 50}},
        {"labelSize": {**_DK11201, "widthMm": True}},
    ],
)
def test_parse_job_refuses_a_bad_label_page(extra):
    with pytest.raises(JobRejected):
        parse_job(_payload(**extra))


def test_label_size_is_refused_on_other_templates():
    with pytest.raises(JobRejected):
        parse_job({"body": "x", "templateId": "circuits", "outputFormat": "pdf", "lane": "Weft", "labelSize": _DK11201})


def test_compose_writes_label_macros_not_the_page_hook():
    tex = compose("stocklabel", "InstruMeasure", "X", _OWNED, label_size=(62.0, 28.9, 1.55, 3.0))
    assert "\\def\\EndleafLabelW{62.00}" in tex
    assert "\\def\\EndleafLabelMY{3.00}" in tex
    assert "endleaf-page.tex" not in tex
    assert "\\input{endleaf-label.tex}" in tex


def test_template_fonts_have_no_tex_ligatures():
    text = (_TEX / "endleaf-label.tex").read_text(encoding="utf-8")
    assert "Ligatures=TeX" not in text
    assert text.count("Ligatures=NoCommon") == 2
    assert "endleaf-type.tex" not in (_OWNED / "stocklabel/preamble.tex").read_text(encoding="utf-8")


def test_example_body_passes_the_source_policy():
    reject_forbidden_source(example_body("stocklabel", _OWNED))


def test_label_fit_map_reads_rows_and_distinct_missing_glyphs():
    log = (
        "ENDLEAF_LABELFIT 1 name 11.5pt - ok\n"
        "ENDLEAF_LABELFIT 1 spec 6pt package,current ok\n"
        "ENDLEAF_LABELFIT 1 stock 6pt - ok\n"
        "ENDLEAF_LABELFIT 2 name 9pt - over\n"
        "Missing character: There is no X in font texgyreheros-bold!\n"
        "Missing character: There is no X in font texgyreheros-bold!\n"
    )
    mapping = label_fit_map(log)
    assert mapping["labelFit"] == [
        [1, "name", 11.5, "-", "ok"],
        [1, "spec", 6.0, "package,current", "ok"],
        [1, "stock", 6.0, "-", "ok"],
        [2, "name", 9.0, "-", "over"],
    ]
    assert mapping["glyphs"] == 1
    line = label_fit_line(log)
    encoded = parse_layout_map(line)
    assert decode_map(encoded) == mapping
    assert label_fit_map("no rows") is None


def _compile(tmp_path, body, label_size):
    tex = compose("stocklabel", "InstruMeasure", body, _OWNED, label_size=label_size)
    (tmp_path / "job.tex").write_text(tex, encoding="utf-8")
    env = {"TEXINPUTS": f"{_TEX}//:", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    done = subprocess.run(
        ["xelatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "job.tex"],
        cwd=tmp_path, env=env, capture_output=True, timeout=120, check=False,
    )
    log = (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")
    assert done.returncode == 0, log[-2000:]
    return (tmp_path / "job.pdf").read_bytes(), log


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_example_label_page_size_rows_and_no_overfull(tmp_path):
    data, log = _compile(tmp_path, example_body("stocklabel", _OWNED), (89.8, 29.0, 2.95, 1.55))
    width, height = _mediabox_pt(data)
    assert abs(width - 89.8 * _MM) < 0.1 and abs(height - 29.0 * _MM) < 0.1
    assert "Overfull" not in log
    mapping = label_fit_map(log)
    # ENDLEAF-R66-FIT contract: the rows the gate expects for its example job.
    assert mapping["labelFit"] == _CONTRACT["labelFit"]
    assert mapping["glyphs"] == 0


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_contract_label_size_is_what_parse_job_accepts():
    job = parse_job(_payload(labelSize=_CONTRACT["labelSize"]))
    assert job.label_size == (89.8, 29.0, 2.95, 1.55)
    assert {key: _CONTRACT[key] for key in ("templateId", "outputFormat", "lane")} == {
        "templateId": job.template_id, "outputFormat": job.output_format, "lane": job.lane,
    }


def _label(name, spec=("", "", "", "", "", ""), stock="1"):
    rects = "\\q{4}{4}{11}{11}"
    return "\\def\\EndleafQrRects{" + rects + "}%\n\\EndleafStockLabel{81}{" + name + "}" + "".join(
        "{" + part + "}" for part in spec
    ) + "{" + stock + "}\n"


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_name_shrinks_to_nine_pt_then_reports_over(tmp_path):
    long_name = "W" * 14
    longer = "W" * 30
    body = _label("Short") + _label(long_name) + _label(longer)
    _data, log = _compile(tmp_path, body, (89.8, 29.0, 2.95, 1.55))
    rows = {(row[0], row[1]): row for row in label_fit_map(log)["labelFit"]}
    assert rows[(1, "name")][2] == 16.0 and rows[(1, "name")][4] == "ok"
    assert 9.0 <= rows[(2, "name")][2] < 16.0 and rows[(2, "name")][4] == "ok"
    assert rows[(3, "name")][2] == 9.0 and rows[(3, "name")][4] == "over"


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_spec_drops_package_then_current(tmp_path):
    spec = ("DC-DC converter", "24V\\textrightarrow{}5V", "200mA", "1W", "Iso 1.5kV", "SIP-7")
    _data, log = _compile(tmp_path, _label("A", spec), (62.0, 28.9, 1.55, 3.0))
    row = [r for r in label_fit_map(log)["labelFit"] if r[1] == "spec"][0]
    assert row[3] == "package,current"
    assert row[2] == 6.0 and row[4] == "over"


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_spec_drops_only_package_when_that_is_enough(tmp_path):
    spec = ("DC-DC", "24V\\textrightarrow{}5V", "", "", "", "SIP-7 long package")
    _data, log = _compile(tmp_path, _label("A", spec), (62.0, 28.9, 1.55, 3.0))
    row = [r for r in label_fit_map(log)["labelFit"] if r[1] == "spec"][0]
    assert row[3] == "package" and row[2] == 7.0 and row[4] == "ok"


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")
def test_one_label_per_page(tmp_path):
    data, _log = _compile(tmp_path, _label("A") + _label("B") + _label("C"), (89.8, 29.0, 2.95, 1.55))
    (tmp_path / "out.pdf").write_bytes(data)
    info = subprocess.run(["pdfinfo", str(tmp_path / "out.pdf")], capture_output=True, text=True, check=True).stdout
    assert re.search(r"^Pages:\s+3$", info, re.MULTILINE)
