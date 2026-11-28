"""Run the Python reference checker on one fixture (helper of make_gap_fixtures.py).

Usage (with the pinned reference interpreter, from anywhere):
  gap_ref.py REPO PDF SPEC.json  ->  one JSON object {"items", "log", "lines"} on stdout

SPEC.json: {"template", "blocks": {"page": [l, t, w, h]}, "texPages": [], "marks": [], "shellPages": {}}.
"lines" is the per-page line dump in the shape of `endleaf-pdfcheck --dump`:
[[page, text, [x0, top, x1, bottom]], ...].
Budgets are lifted so the answer does not depend on the machine.
"""
import json
import pathlib
import sys

repo, pdf, spec_path = sys.argv[1:4]
sys.path.insert(0, repo)
import colophon.pdf_layout_check as m  # noqa: E402

spec = json.loads(pathlib.Path(spec_path).read_text())
data = pathlib.Path(pdf).read_bytes()
blocks = {int(k): tuple(v) for k, v in spec.get("blocks", {}).items()}
result = m.check_pdf(
    data,
    template_id=spec.get("template", ""),
    blocks=blocks,
    marks=[list(r) for r in spec.get("marks", [])] or None,
    shell_pages={int(k): v for k, v in spec.get("shellPages", {}).items()} or None,
    tex_pages=set(spec.get("texPages", [])),
    page_budget=1e9,
    document_budget=1e9,
)
lines = []
try:
    for raw in m.extract_pages(data):
        index, width, height, glyphs, paths, offpage = raw
        page = m._build_page(index, width, height, glyphs, paths, None, "", offpage, [])
        for ln in page.lines:
            lines.append([index, ln.text, [round(float(x), 1) for x in ln.box]])
except Exception:  # an unreadable file has no lines; the items carry the skip note
    lines = []
json.dump({"items": result.items, "log": result.log_lines, "lines": lines}, sys.stdout, ensure_ascii=False)
