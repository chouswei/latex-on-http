# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R60-LAYOUT. Marks in a fulldoc body come back as a page layout map."""

import json
import shutil

import pytest

from colophon.layout_map import (
    LAYOUT_HEADER,
    LAYOUT_MAP_CAP_BYTES,
    decode_map,
    encode_map,
    layout_map,
    parse_layout_map,
)

_NEEDS_TEX = pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex is not installed")

_BODY = (
    "\\section{\\EndleafMark{s1}{s}Intro}\\label{sec:intro}\n"
    "\\EndleafMark{p1}{s}Lorem ipsum dolor sit amet. Figure~\\EndleafMark{fig:a}{r}\\ref{fig:a} shows it."
    " Lorem ipsum dolor sit amet, consectetur adipiscing elit.\\EndleafMark{p1}{e}\n\n"
    "\\begin{figure}[htbp]\n\\EndleafVMark{f1}{s}\\centering\n"
    "\\begin{tikzpicture}\\draw (0,0) rectangle (16,4);\\end{tikzpicture}\n"
    "\\caption{Wide}\\label{fig:a}\n\\EndleafVMark{f1}{e}\\end{figure}\n\n"
    "\\EndleafMark{p2}{s}" + "Long text that fills pages. " * 900 + "\\EndleafMark{p2}{e}\n"
)


def test_layout_map_reads_wrapped_log_lines():
    log = (
        "ENDLEAF_GEOM 845.04684pt 718.77686pt 598.0pt 345.0pt\n"
        "ENDLEAF_PICBOX f1 455.64389pt 114.21097pt\n"
        "ENDLEAF_MARK s1 s 1 46450400 portrait\nENDLEAF_MARK p1 s 1 449570\n30 portrait\n"
        "ENDLEAF_MARK p1 e 2 43384166 landscape\n"
    )
    mapping = layout_map(log)
    assert mapping["geom"] == {"paper": 845.0, "top": 718.8, "textHeight": 598.0, "line": 345.0}
    assert mapping["marks"] == [["s1", "s", 1, 708.8, "p"], ["p1", "s", 1, 686.0, "p"], ["p1", "e", 2, 662.0, "l"]]
    assert mapping["pictures"] == [["f1", 455.6, 114.2]]
    assert layout_map("no marks here") is None


def test_encoded_map_round_trips_and_is_capped():
    mapping = {"v": 1, "geom": {}, "marks": [["p1", "s", 1, 1.0, "p"]], "pictures": []}
    encoded = encode_map(mapping)
    assert decode_map(encoded) == mapping
    assert parse_layout_map("x\nENDLEAF_LAYOUTMAP " + encoded + "\n") == encoded
    assert parse_layout_map("ENDLEAF_LAYOUTMAP not!base64") is None
    big = {"v": 1, "geom": {}, "marks": [[f"p{i}", "s", i, float(i), "p"] for i in range(20000)], "pictures": []}
    assert encode_map(big) is None
    assert encode_map(big, cap=10**7) is not None and len(encode_map(big, cap=10**7)) > LAYOUT_MAP_CAP_BYTES


def test_response_carries_the_layout_header(config, switch_path, monitor, auth):
    from colophon.killswitch import KillSwitch
    from colophon.runner import Outcome, Supervisor
    from colophon.worker import create_app
    from tests.colophon.conftest import valid_body

    encoded = encode_map({"v": 1, "geom": {}, "marks": [["p1", "s", 1, 1.0, "p"]], "pictures": []})
    outcome = Outcome(kind="ok", body=b"%PDF-1.4", content_type="application/pdf", wall_sec=0.5, layout_map=encoded)

    class _Runner:
        def __call__(self, job, name, abort_event):
            return outcome

    app = create_app(config, KillSwitch(switch_path), monitor, Supervisor(_Runner(), 10))
    response = app.test_client().post("/v1/jobs", json=valid_body(), headers=auth)
    assert response.headers[LAYOUT_HEADER] == encoded
    plain = Outcome(kind="ok", body=b"%PDF-1.4", content_type="application/pdf", wall_sec=0.5)
    outcome = plain
    response = app.test_client().post("/v1/jobs", json=valid_body(), headers=auth)
    assert LAYOUT_HEADER not in response.headers


@_NEEDS_TEX
def test_sandbox_returns_the_layout_map_of_a_marked_body(tmp_path, monkeypatch):
    from tests.colophon.conftest import valid_body
    from tests.colophon.test_fulldoc import _bind_tex, _render

    _bind_tex(monkeypatch, tmp_path)
    code, pdf, err = _render(valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=_BODY), monkeypatch)
    assert code == 0, err[-2000:]
    encoded = parse_layout_map(err)
    assert encoded, err[-2000:]
    mapping = decode_map(encoded)
    marks = {(m[0], m[1]): m for m in mapping["marks"]}
    assert marks[("s1", "s")][2] == 1 and marks[("p1", "e")][2] == 1
    assert marks[("fig:a", "r")][2] == 1
    # p2 is long: it starts on page 1 and ends on a later page.
    assert marks[("p2", "e")][2] > marks[("p2", "s")][2]
    # The figure's top is above its bottom; the picture is wider than the line.
    assert marks[("f1", "s")][3] > marks[("f1", "e")][3]
    (picture,) = mapping["pictures"]
    assert picture[0] == "f1" and picture[1] > mapping["geom"]["line"]
    # Ids, tags, pages and positions only: no document text.
    assert "Lorem" not in json.dumps(mapping)


@_NEEDS_TEX
def test_unmarked_body_has_no_map_and_marks_do_not_move_text(tmp_path, monkeypatch):
    from tests.colophon.conftest import valid_body
    from tests.colophon.test_fulldoc import _bind_tex, _render

    _bind_tex(monkeypatch, tmp_path)
    plain = _BODY.replace("\\EndleafMark{", "\\EndleafNoMark{").replace("\\EndleafVMark{", "\\EndleafNoMark{")
    plain = "\\newcommand\\EndleafNoMark[2]{}\n" + plain
    code, plain_pdf, err = _render(valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=plain), monkeypatch)
    assert code == 0, err[-2000:]
    assert parse_layout_map(err) is None
    code, marked_pdf, err = _render(valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=_BODY), monkeypatch)
    assert code == 0
    import subprocess

    def text_of(pdf, name):
        path = tmp_path / name
        path.write_bytes(pdf)
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout

    assert text_of(plain_pdf, "plain.pdf") == text_of(marked_pdf, "marked.pdf")
