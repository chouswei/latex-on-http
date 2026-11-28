#!/usr/bin/env python3
"""bench_arm.py MODE(idle|loaded) OUT.json. Stdlib only. BENCH_ROOT holds venv311/ (the pinned wheels), bin/pyone.py, bin/endleaf-pdfcheck and py/ (colophon/ + the 21 sample PDFs + pdfs.txt). loaded = 3 busy-loop processes on the other cores."""
import json, os, statistics as st, subprocess, sys, time
P = os.path.expanduser(os.environ.get("BENCH_ROOT", "~/endleaf-rust-proto"))
PY = [f"{P}/venv311/bin/python", f"{P}/bin/pyone.py", f"{P}/py"]
RB = f"{P}/bin/endleaf-pdfcheck"
pdfs = [l.strip() for l in open(f"{P}/py/pdfs.txt") if l.strip()]
mode, out = sys.argv[1], sys.argv[2]
RUNS = 3
hogs = []
if mode == "loaded":
    for _ in range(3):
        hogs.append(subprocess.Popen(["python3", "-c", "while True: pass"]))
    time.sleep(2)
def run(cmd):
    t = time.perf_counter(); p = subprocess.run(cmd, cwd=f"{P}/py", capture_output=True, text=True); w = time.perf_counter() - t
    if p.returncode: raise SystemExit(f"FAIL {cmd}: {p.stderr[-2000:]}")
    return w, json.loads(p.stdout.strip().splitlines()[-1])
res = {"mode": mode, "loadavg_start": open("/proc/loadavg").read().split()[:3], "docs": {}}
try:
    for f in pdfs:
        d = res["docs"][f] = {"py_cold": [], "rs_cold": []}
        for _ in range(RUNS):
            w, j = run(PY + [f, "1"]); d["py_cold"].append({"proc": w, "check": j["runs"][0], "import": j["import_sec"]})
            d["pages"] = j["pages"]; d["py_items"] = j["items"]; d["py_default_codes"] = j["default_codes"]
            w, j = run([RB, "--page-budget", "1e9", "--doc-budget", "1e9", f]); d["rs_cold"].append({"proc": w, "check": j["sec"], "page_sec": j["page_sec"]})
            d["rs_items"] = j["items"]; d["rs_pages"] = j["pages"]
        w, j = run(PY + [f, str(RUNS + 1)]); d["py_warm"] = j["runs"][1:]
        w, j = run([RB, "--page-budget", "1e9", "--doc-budget", "1e9", "--repeat", str(RUNS + 1), f]); d["rs_warm"] = j["runs_sec"][1:]
        w, j = run([RB, f]); d["rs_default_codes"] = [i["code"] for i in j["items"]]; d["rs_default_proc"] = w
finally:
    res["loadavg_end"] = open("/proc/loadavg").read().split()[:3]
    for h in hogs: h.kill()
try: res["temp"] = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True).stdout.strip()
except Exception: pass
json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
print("done", out)
