"""Synthetic parity: the constructed PDFs of tests/colophon/test_pdf_layout_check_r81.py,
run through the Python checker and the Rust binary.

Usage (from the repo root): synth_cases.py REPO BINARY OUTDIR
Writes OUTDIR/<case>.pdf plus OUTDIR/<case>.json (template, blocks, texPages), runs both
checkers and prints a Markdown table of per-case code agreement (and full item agreement:
code, page, overMm, box within 0.5 pt, message). Exit 1 on any code disagreement.
"""
import json
import pathlib
import subprocess
import sys
import types

repo, binary, outdir = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
sys.path.insert(0, repo)
if "pytest" not in sys.modules:
    try:
        import pytest  # noqa: F401
    except ImportError:  # the test module only needs these two names at import time
        stub = types.ModuleType("pytest")
        stub.importorskip = lambda name, *a, **k: __import__(name)
        stub.mark = types.SimpleNamespace(skipif=lambda *a, **k: (lambda f: f))
        sys.modules["pytest"] = stub
sys.path.insert(0, str(pathlib.Path(repo) / "tests" / "colophon"))
import test_pdf_layout_check_r81 as t  # noqa: E402

from colophon.pdf_layout_check import check_pdf  # noqa: E402

B = t._BLOCK
page_margin = t.text(72, 700, "short") + t.text(400, 680, "this line runs far past the right edge of the block")
node = "0.5 w 100 600 80 30 re S\n"
stroke = "0.5 w 60 604 m 300 604 l S\n"
label = t.text(100, 600, "Pressure")
figure = "0.5 w 80 580 200 60 re S\n"
gutter = t.text(100, 600, "Alpha", 10) + t.text(100 + 25.7 + 0.4, 600, "Beta", 8)
stray = t.body(5) + t.text(72, 500, "```python") + t.text(72, 440, "\\\\begin{figure} printed")
faulty = t.text(400, 680, "this line runs far past the right edge of the block")
ten = "".join(t.text(400, 770 - 30 * n, "this line runs far past the right edge of the block") for n in range(14))
three = "".join(t.text(400, 700 - 12 * n, "this line runs far past the right edge of the block") for n in range(3))

# (name, pages, template, blocks, tex_pages)
CASES = [
    ("clean_page", [t.body() + t.text(400, 40, "1")], "fulldoc", {1: B}, ()),
    ("margin_escape", [page_margin], "fulldoc", {1: B}, ()),
    ("margin_escape_noblock", [page_margin], "fulldoc", {}, ()),
    ("caption_overlap", [t.body(10) + t.text(72, 400, "Figure 1: the pump curve") + "0.5 g 60 395 200 40 re f\n"], "fulldoc", {1: B}, ()),
    ("label_on_stroke", [stroke + label], "fulldoc", {1: B}, ()),
    ("label_on_stroke_white_cover", [stroke + "1 g 95 595 60 16 re f 0 g\n" + label], "fulldoc", {1: B}, ()),
    ("text_escapes_node", [node + t.text(160, 610, "Overflow")], "fulldoc", {1: B}, ()),
    ("text_inside_node", [node + t.text(105, 610, "Inside")], "fulldoc", {1: B}, ()),
    ("text_overlap", [t.text(100, 600, "Alpha") + t.text(112, 600, "Beta")], "fulldoc", {1: B}, ()),
    ("text_overlap_extensible", [t.text(100, 600, "---") + t.text(103, 600, "---")], "fulldoc", {1: B}, ()),
    ("label_gutter_sysml", [figure + gutter], "sysml", {1: B}, ()),
    ("label_gutter_plots", [figure + gutter], "plots", {1: B}, ()),
    ("stray_source_shell", [stray], "document-shell", {1: B}, ()),
    ("stray_source_plots", [stray], "plots", {1: B}, ()),
    ("empty_page_inside", [t.text(72, 700, "two") + t.text(150, 700, "words"), t.body(), t.body()], "fulldoc", {1: B, 2: B, 3: B}, ()),
    ("empty_page_drawn", ["0.5 w 100 500 m 300 500 l S\n" + t.text(72, 700, "two words"), t.body()], "fulldoc", {1: B, 2: B}, ()),
    ("empty_page_last_words", [t.body(), t.text(72, 700, "two words")], "fulldoc", {1: B, 2: B}, ()),
    ("empty_page_last_blank", [t.body(), ""], "fulldoc", {1: B, 2: B}, ()),
    ("warning_item", [faulty], "fulldoc", {1: B}, ()),
    ("cap_at_ten", [ten], "fulldoc", {1: B}, ()),
    ("dedupe_three", [three], "fulldoc", {1: B}, ()),
    ("dedupe_tex_pages", [three], "fulldoc", {1: B}, (1,)),
    ("offpage_dropped", [t.body(5) + t.text(900, 400, "hidden") + t.text(-300, 400, "gone")], "fulldoc", {1: B}, ()),
    ("docstrum_guard", ["".join(t.text(72, 700 - 14 * n, "aaaa bbbb cccc dddd eeee ffff gggg") for n in range(8))], "fulldoc", {1: B}, ()),
    ("budget_two_pages", [faulty, t.body()], "fulldoc", {1: B, 2: B}, ()),
    ("garbage", None, "fulldoc", {}, ()),
]


def same(a, b):
    keys = ("code", "page", "overMm", "message", "regionCount", "count")
    if any(a.get(k) != b.get(k) for k in keys):
        return False
    ba, bb = a.get("box"), b.get("box")
    return (ba is None and bb is None) or (ba is not None and bb is not None and all(abs(x - y) <= 0.5 for x, y in zip(ba, bb)))


outdir.mkdir(parents=True, exist_ok=True)
rows, bad = [], 0
for name, pages, template, blocks, tex_pages in CASES:
    data = b"not a pdf" if pages is None else t.pdf(pages)
    pdf_path = outdir / f"{name}.pdf"
    pdf_path.write_bytes(data)
    side = {"template": template, "blocks": {str(k): list(v) for k, v in blocks.items()}, "texPages": list(tex_pages)}
    (outdir / f"{name}.json").write_text(json.dumps(side))
    blocks_path = outdir / f"{name}.blocks.json"
    blocks_path.write_text(json.dumps(side["blocks"]))
    py = check_pdf(data, template_id=template, blocks=blocks, tex_pages=set(tex_pages), page_budget=1e9, document_budget=1e9)
    cmd = [binary, "--page-budget", "1e9", "--doc-budget", "1e9", "--template", template, "--blocks", str(blocks_path)]
    if tex_pages:
        cmd += ["--tex-pages", ",".join(map(str, tex_pages))]
    rust = json.loads(subprocess.run(cmd + [str(pdf_path)], capture_output=True, text=True, check=True).stdout)
    pc, rc = [i["code"] for i in py.items], [i["code"] for i in rust["items"]]
    full = len(py.items) == len(rust["items"]) and all(same(a, b) for a, b in zip(py.items, rust["items"]))
    logs = py.log_lines == rust["log"]
    bad += pc != rc
    rows.append((name, template, ",".join(pc) or "-", ",".join(rc) or "-", "yes" if pc == rc else "NO", "yes" if full else "no", "yes" if logs else "no"))
print("| case | template | python codes | rust codes | codes agree | items agree | log agrees |")
print("|---|---|---|---|---|---|---|")
for r in rows:
    print("| " + " | ".join(r) + " |")
print(f"\n{len(rows) - bad}/{len(rows)} cases agree on codes")
sys.exit(1 if bad else 0)
