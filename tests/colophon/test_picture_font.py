"""ENDLEAF-R62-FONT: a picture-level font size reaches node text in fulldoc, and nodes stay in the Endleaf sans."""

import re
import shutil
import subprocess

import pytest

from colophon.layout_map import decode_map, parse_layout_map

pytestmark = pytest.mark.skipif(
    shutil.which("xelatex") is None or shutil.which("pdftotext") is None, reason="xelatex or pdftotext is not installed"
)


def _figure(part, options, node_options, word):
    return (
        "\\begin{figure}[htbp]\n\\EndleafVMark{%s}{s}\\centering\n"
        "\\begin{tikzpicture}[%s]\\node[%s] at (0,0) {%s};\\end{tikzpicture}\n"
        "\\caption{C}\n\\EndleafVMark{%s}{e}\\end{figure}\n\n" % (part, options, node_options, word, part)
    )


def _heights(pdf_path):
    out = subprocess.run(["pdftotext", "-bbox", str(pdf_path), "-"], capture_output=True, text=True, check=True).stdout
    found = {}
    for match in re.finditer(r'yMin="([0-9.]+)" xMax="[0-9.]+" yMax="([0-9.]+)">([A-Za-z]+)<', out):
        found[match.group(3)] = float(match.group(2)) - float(match.group(1))
    return found


def test_picture_level_font_size_reaches_node_text(tmp_path, monkeypatch):
    from tests.colophon.conftest import valid_body
    from tests.colophon.test_fulldoc import _bind_tex, _render

    _bind_tex(monkeypatch, tmp_path)
    body = (
        _figure("f1", "font=\\large", "", "PictureLarge")
        + _figure("f2", "", "font=\\large", "NodeLarge")
        + _figure("f3", "", "", "Plain")
        + _figure("f4", "every node/.style={font=\\Large}", "", "EveryNodeLarge")
    )
    code, pdf, err = _render(valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=body), monkeypatch)
    assert code == 0, err[-2000:]
    fits = {fit[0]: fit[3] for fit in decode_map(parse_layout_map(err))["fits"]}
    # \large is 12 pt and \Large 14.4 pt in the 10 pt body; before R62 the picture-level \large measured (and set) 10.
    assert fits == {"f1": 12.0, "f2": 12.0, "f3": 10.0, "f4": 14.4}
    path = tmp_path / "out.pdf"
    path.write_bytes(pdf)
    heights = _heights(path)
    assert heights["PictureLarge"] == pytest.approx(heights["NodeLarge"], abs=0.2)
    assert heights["PictureLarge"] > heights["Plain"] * 1.15
    fonts = subprocess.run(["pdffonts", str(path)], capture_output=True, text=True).stdout
    assert "TeXGyreHeros" in fonts
