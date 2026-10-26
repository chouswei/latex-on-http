"""ENDLEAF-R69-WHERE: page, landscape turn and superseded overfull rows (TeX-free)."""

from pathlib import Path

from colophon.layout_map import layout_map
from colophon.layout_warn import layout_warnings, picture_pages, turned_pictures
from colophon.overfull import overfull_rows

_TEX = Path(__file__).resolve().parents[2] / "colophon/share/tex/latex/colophon-v1"

# A 22 cm figure turned its float landscape and shipped alone on page 2.
# Landscape A4 line 594pt; picture 627.7pt (33.9pt, 11.9 mm over).
_LOG = (
    "ENDLEAF_GEOM 845.04684pt 72.0pt 614.0pt 345.0pt\n"
    "ENDLEAF_PICFIT - plain 628.0pt 594.0pt 10.0\n"
    "ENDLEAF_PICTURN 1 12\n"
    "Overfull \\hbox (282.7pt too wide) in paragraph at lines 10--14\n"
    " []\n\n"
    "[1] ENDLEAF_PICPAGE 1 2 landscape\n[2]\n"
)


def test_page_and_turn_are_read_by_picture_number():
    assert picture_pages(_LOG) == {1: (2, "landscape")}
    assert turned_pictures(_LOG) == {1: 12}


def test_warning_carries_page_landscape_and_no_landscape_advice():
    (item,) = layout_warnings(_LOG)
    assert item["page"] == 2 and item["landscape"] is True
    assert item["message"].startswith("pg2 landscape: a picture runs 11.9 mm past the text line")
    assert item["overMm"] == 11.9
    assert item["fix"].startswith("already landscape; scale inside the source to 0.94")
    assert "orientation" not in item["message"]


def test_unturned_picture_keeps_old_message_shape():
    log = "ENDLEAF_PICFIT f1 plain 400pt 345pt 10.0\n[1] ENDLEAF_PICPAGE 1 1 portrait\n"
    (item,) = layout_warnings(log)
    assert item["message"].startswith("f1 pg1: a picture runs")
    assert "landscape" not in item and item["fix"].startswith("scale inside the source")


def test_portrait_overfull_row_of_the_turned_picture_is_superseded():
    rows, total = overfull_rows(_LOG, body_start=1, body_lines=100, turned_lines=(12,))
    assert total == 1 and rows[0]["superseded"] == "landscape"
    rows, _ = overfull_rows(_LOG, body_start=1, body_lines=100, turned_lines=(40,))
    assert "superseded" not in rows[0]


def test_layout_map_marks_the_row():
    log = _LOG + "ENDLEAF_MARK p1 s 1 100 portrait\n"
    mapping = layout_map(log, body_start=1, body_lines=100)
    assert mapping["overfull"][0]["superseded"] == "landscape"


def test_layout_tex_logs_turn_and_shipout_page():
    tex = (_TEX / "endleaf-layout.tex").read_text()
    assert r"\global\advance\ellay@picn\@ne" in tex
    assert "ENDLEAF_PICTURN" in tex and "ENDLEAF_PICPAGE" in tex
    assert r"\noexpand\thepage" in tex
    close = tex[tex.index(r"\def\elfit@closetizpicture{") :]
    order = [close.index(k) for k in (r"\elfit@plainfit", r"\ellay@turnline", r"\ellay@fit{plain}", r"\ellay@turned", r"\ellay@pagemark")]
    assert order == sorted(order)
    assert r"\elfit@plainline=\elfit@landline" in tex
