"""Per-page internals of the Python checker, in the shape of `endleaf-pdfcheck --dump`.

Usage (from the repo root): py_dump.py REPO PDF... > py-dump.jsonl
One JSON line per page: glyph, word, line and path counts and each line's text and box.
"""
import json
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
import colophon.pdf_layout_check as m  # noqa: E402

for name in sys.argv[2:]:
    data = pathlib.Path(name).read_bytes()
    for raw in m.extract_pages(data):
        index, width, height, glyphs, paths, offpage = raw
        page = m._build_page(index, width, height, glyphs, paths, None, "", offpage, [])
        print(
            json.dumps(
                {
                    "file": name,
                    "page": index,
                    "glyphs": len(page.glyphs),
                    "words": len(page.words),
                    "lines": len(page.lines),
                    "paths": len(page.paths),
                    "line_items": [[ln.text, [round(float(x), 1) for x in ln.box]] for ln in page.lines],
                },
                ensure_ascii=False,
            )
        )
