"""Compare py_dump.py and `endleaf-pdfcheck --dump` output page by page.

Usage: compare_dump.py PY.jsonl RUST.jsonl
A Python line is matched by a Rust line with the same text and every box edge within 0.5 pt
(order-free); the table counts the Python lines with no match.
"""
import json
import sys
from collections import defaultdict


def load(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            out[(row["file"], row["page"])] = row
    return out


py, rust = load(sys.argv[1]), load(sys.argv[2])
per_file = defaultdict(lambda: [0, 0, 0, 0, 0, 0])  # pages, count diffs, lines, unmatched py, unmatched rust, pages missing
for key, p in py.items():
    f = per_file[key[0]]
    f[0] += 1
    r = rust.get(key)
    if r is None:
        f[5] += 1
        continue
    if any(p[k] != r[k] for k in ("glyphs", "words", "lines", "paths")):
        f[1] += 1
    f[2] += len(p["line_items"])
    left = list(r["line_items"])
    for text, box in p["line_items"]:
        hit = next(
            (n for n, (t, b) in enumerate(left) if t == text and all(abs(x - y) <= 0.5 for x, y in zip(b, box))),
            None,
        )
        if hit is None:
            f[3] += 1
        else:
            left.pop(hit)
    f[4] += len(left)
print("| pdf | pages | pages with count diffs | py lines | py lines unmatched | rust lines unmatched |")
print("|---|---|---|---|---|---|")
tot = [0] * 6
for name, f in per_file.items():
    print(f"| {name} | {f[0]} | {f[1]} | {f[2]} | {f[3]} | {f[4]} |")
    tot = [a + b for a, b in zip(tot, f)]
print(f"| total | {tot[0]} | {tot[1]} | {tot[2]} | {tot[3]} | {tot[4]} |")
