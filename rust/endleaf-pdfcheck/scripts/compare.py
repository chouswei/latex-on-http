"""Diff the Python reference (pyref.py JSON) and the Rust JSON lines, item by item.

Usage: compare.py PYREF.json RUST.jsonl
An item matches when code, page and overMm are equal and every box edge is within 0.5 pt.
Messages and worker log lines are compared too and reported in their own columns.
Exit status 1 when any file differs.
"""
import json
import sys


def load(py_path, rust_path):
    py = json.load(open(py_path, encoding="utf-8"))["docs"]
    rust = {}
    for line in open(rust_path, encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            rust[row["file"]] = row
    return py, rust


def same(a, b):
    if a.get("code") != b.get("code") or a.get("page") != b.get("page"):
        return False
    if a.get("overMm") != b.get("overMm"):
        return False
    ba, bb = a.get("box"), b.get("box")
    if (ba is None) != (bb is None):
        return False
    return ba is None or all(abs(x - y) <= 0.5 for x, y in zip(ba, bb))


def main():
    py, rust = load(sys.argv[1], sys.argv[2])
    rows, bad = [], 0
    for name in py:
        p, r = py[name], rust.get(name)
        if r is None:
            rows.append((name, len(p["items"]), "-", "-", "missing", "-", "-"))
            bad += 1
            continue
        pi, ri = p["items"], r["items"]
        matched = sum(1 for a, b in zip(pi, ri) if same(a, b))
        msg = all(a.get("message") == b.get("message") for a, b in zip(pi, ri))
        log = p["log"] == r["log"]
        ok = matched == len(pi) == len(ri) and msg and log
        bad += not ok
        rows.append((name, len(pi), len(ri), matched, "ok" if ok else "DIFF", "yes" if msg else "no", "yes" if log else "no"))
    head = ("pdf", "py items", "rust items", "matched", "result", "messages", "log")
    width = max(len(r[0]) for r in rows + [head])
    print(f"| {head[0]:<{width}} | " + " | ".join(head[1:]) + " |")
    print(f"|{'-' * (width + 2)}|" + "|".join("-" * (len(h) + 2) for h in head[1:]) + "|")
    for r in rows:
        print(f"| {r[0]:<{width}} | " + " | ".join(f"{str(v):<{len(h)}}" for v, h in zip(r[1:], head[1:])) + " |")
    print(f"\n{len(rows) - bad}/{len(rows)} PDFs agree")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
