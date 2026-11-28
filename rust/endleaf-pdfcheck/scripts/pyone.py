"""pyone.py REPO PDF REPEAT -> JSON: import_sec, pages, runs[sec] (budgets lifted), items of run 1, default-budget codes."""
import sys, time, json, pathlib
t0 = time.perf_counter()
sys.path.insert(0, sys.argv[1])
import colophon.pdf_layout_check as m
m._preload()
imp = time.perf_counter() - t0
data = pathlib.Path(sys.argv[2]).read_bytes(); rep = int(sys.argv[3])
runs, items = [], None
for k in range(rep):
    a = time.perf_counter(); r = m.check_pdf(data, page_budget=1e9, document_budget=1e9); runs.append(time.perf_counter() - a)
    if items is None: items = r.items
d = m.check_pdf(data)
print(json.dumps({"import_sec": imp, "pages": m._page_count(data), "runs": runs, "items": items,
                  "default_codes": [i["code"] for i in d.items]}, ensure_ascii=False))
