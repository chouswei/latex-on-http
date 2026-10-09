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


# -- ENDLEAF-R61 ----------------------------------------------------------------------------------------------
def _wide(part, width_cm, size_command):
    return (
        "\\begin{figure}[htbp]\n\\EndleafVMark{" + part + "}{s}\\centering\n"
        "\\begin{tikzpicture}\\draw (0,0) rectangle (" + str(width_cm) + ",2);"
        "\\node[font=" + size_command + "] at (1,1) {Label};\\node[font=" + size_command + "] at (3,1) {Other};\\end{tikzpicture}\n"
        "\\caption{Wide}\\label{fig:" + part + "}\n\\EndleafVMark{" + part + "}{e}\\end{figure}\n\n"
    )


def test_map_optional_lists_and_their_drop_order():
    log = (
        "ENDLEAF_GEOM 845pt 718pt 598pt 345pt\n"
        "ENDLEAF_PICFIT f1 plain 499.0pt 345.0pt 12\nENDLEAF_PICFIT - plain 400pt 345pt 10\n"
        "ENDLEAF_MARK p1 s 1 46450400 portrait\n"
        "Overfull \\hbox (3.5pt too wide) in paragraph at lines 40--42\n"
        "Overfull \\hbox (9.0pt too wide) in paragraph at lines 3--4\n"
    )
    aux = "\\newlabel{fig:a}{{3}{5}{Wide}{figure.caption.3}{}}\n\\newlabel{sec:b}{{2.1}{4}}\n"
    mapping = layout_map(log, body_start=30, body_lines=20, aux=aux)
    assert mapping["fits"] == [["f1", 499.0, 345.0, 12.0]]
    # Line 40 of job.tex is body line 11; line 3 is in the preamble, so it is not located.
    assert mapping["overfull"] == [[11, 3.5]]
    assert mapping["labels"] == [["fig:a", "3", 5], ["sec:b", "2.1", 4]]
    assert "overfull" not in layout_map(log, aux=aux)
    full = encode_map(mapping)
    assert decode_map(full)["labels"]
    many = dict(mapping, labels=[[f"l{i}", str(i), i] for i in range(400)])
    size_without_labels = len(encode_map({k: v for k, v in many.items() if k != "labels"}))
    squeezed = decode_map(encode_map(many, cap=size_without_labels))
    assert "labels" not in squeezed and squeezed["fits"] and squeezed["marks"]


def test_picture_fit_scale_and_floor():
    from colophon.layout_warn import layout_warnings, picture_fit

    assert picture_fit(499.0, 345.0, 12.0) == (0.69, 8.2, False)
    assert picture_fit(700.0, 345.0, 10.0) == (0.49, 4.9, True)
    assert picture_fit(700.0, 345.0, 99) == (0.49, None, False)
    fits, floor = layout_warnings(
        "ENDLEAF_PICFIT f1 plain 499.0pt 345.0pt 12\nENDLEAF_PICFIT f2 plain 700pt 345pt 10\n"
        "ENDLEAF_PICFIT f3 plain 345.5pt 345pt 10\nENDLEAF_WIDE_PICTURE width=499.0pt line=345.0pt\n"
    )
    assert fits["partId"] == "f1" and fits["fix"] == "scale inside the source to 0.69"
    assert fits["belowTypeFloor"] is False and fits["minTextPt"] == 8.2 and fits["overMm"] == 54.1
    assert floor["belowTypeFloor"] is True
    assert floor["fix"] == "redraw or split; scaling would put text at 4.9 pt"
    assert "f2: a picture runs" in floor["message"] and "(below 7 pt)" in floor["message"]


@_NEEDS_TEX
def test_sandbox_measures_picture_text_and_locates_overfull_lines(tmp_path, monkeypatch):
    from colophon.layout_warn import parse_layout
    from tests.colophon.conftest import valid_body
    from tests.colophon.test_fulldoc import _bind_tex, _render

    _bind_tex(monkeypatch, tmp_path)
    body = (
        "\\section{\\EndleafMark{s1}{s}Intro}\\label{sec:intro}\n"
        "\\EndleafMark{p1}{s}See Figure~\\EndleafMark{fig:f1}{r}\\ref{fig:f1}.\\EndleafMark{p1}{e}\n\n"
        + _wide("f1", 17.5, "\\large")
        + _wide("f2", 26, "\\normalsize")
        + _wide("f3", 6, "\\tiny")
        + "\\EndleafMark{p2}{s}\\hbox{Averyveryveryveryveryverylongunbreakablewordthatcannotfitonthelineatallnomatterwhatwedoabout}\\EndleafMark{p2}{e}\n"
    )
    code, _pdf, err = _render(valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=body), monkeypatch)
    assert code == 0, err[-2000:]
    mapping = decode_map(parse_layout_map(err))
    fits = {fit[0]: fit for fit in mapping["fits"]}
    # The smallest text set inside each picture: \large is 12 pt, \normalsize 10 pt and \tiny 5 pt.
    assert fits["f1"][3] == 12.0 and fits["f2"][3] == 10.0 and fits["f3"][3] == 5.0
    assert fits["f1"][1] > fits["f1"][2] and fits["f3"][1] < fits["f3"][2]
    assert ["fig:f1", "1", 1] in mapping["labels"] and ["sec:intro", "1", 1] in mapping["labels"]
    assert any(line == 6 for line, _pt in mapping.get("overfull", [])), mapping.get("overfull")
    warnings = {item.get("partId"): item for item in parse_layout(err)}
    assert set(warnings) == {"f1", "f2"}
    assert warnings["f1"]["belowTypeFloor"] is False and warnings["f1"]["fix"].startswith("scale inside the source to 0.")
    assert warnings["f2"]["belowTypeFloor"] is True and warnings["f2"]["fix"].startswith("redraw or split")
