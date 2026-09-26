#!/bin/sh
# Live checks for a running Colophon worker. Devicor runs this on the Pi.
#
#   COLOPHON_URL=http://100.64.0.1:8080 \
#   COLOPHON_WORKER_TOKEN=... \
#   COLOPHON_IMAGE=localhost/colophon-render:local \
#   scripts/colophon-negative-tests.sh
#
# COLOPHON_PODMAN defaults to podman.
# The output-cap token is failCapHit (HTTP 413). The worker does not emit
# failOutputCap.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
export COLOPHON_ROOT="$ROOT"
: "${COLOPHON_URL:?set COLOPHON_URL}"
: "${COLOPHON_WORKER_TOKEN:?set COLOPHON_WORKER_TOKEN}"
: "${COLOPHON_IMAGE:?set COLOPHON_IMAGE}"
export COLOPHON_PODMAN="${COLOPHON_PODMAN:-podman}"
exec python3 - "$ROOT" <<'PY'
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(sys.argv[1])
BASE = os.environ["COLOPHON_URL"].rstrip("/")
TOKEN = os.environ["COLOPHON_WORKER_TOKEN"]
IMAGE = os.environ["COLOPHON_IMAGE"]
PODMAN = os.environ["COLOPHON_PODMAN"]
CAP = 20 * 1024 * 1024
# Measured on TeX Live 2023: uncompressed pdf:literal of 400 bytes grows the
# PDF by 455 bytes per iteration, plus about 3170 bytes of fixed overhead.
# 45508 iterations lands about 256 KiB under 20 MiB. 46229 lands about 64 KiB
# over. The wrapper's unused packages added well under 256 KiB in the same
# measurement, so the under-cap job stays under and the over-cap job does not.
UNDER_ITERS = 45508
OVER_ITERS = 46229
SMOKE = (
    "circuits.tex",
    "pgfplots.tex",
    "chemistry.tex",
    "gantt.tex",
    "floorplan.tex",
    "pidcircuit.tex",
)


def fail(message):
    print("FAIL:", message, file=sys.stderr)
    raise SystemExit(1)


def request(method, path, payload=None, timeout=120):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/json",
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            elapsed = time.monotonic() - started
            return response.status, dict(response.headers), body, elapsed
    except urllib.error.HTTPError as exc:
        body = exc.read()
        elapsed = time.monotonic() - started
        return exc.code, dict(exc.headers), body, elapsed


def job(source, kind="tex"):
    return {
        "input": source,
        "inputKind": kind,
        "outputFormat": "pdf",
        "lane": "InstruMeasure",
    }


def expect_json(status, headers, body, elapsed):
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"expected JSON, got {status} {body[:200]!r} ({exc})")


def expansion(iterations):
    chunk = "A" * 400
    return (
        "\\special{dvipdfmx:config z 0}\n"
        "\\newcount\\i\n"
        "\\loop\n"
        f"\\ifnum\\i<{iterations}\n"
        "  \\advance\\i by 1\n"
        "  \\special{pdf:literal (" + chunk + ")}\n"
        "\\repeat\n"
        "Done.\n"
    )


def podman(*args, check=True):
    return subprocess.run(
        [PODMAN, *args],
        check=check,
        capture_output=True,
    )


print("GET /version")
status, _headers, body, _elapsed = request("GET", "/version", timeout=30)
if status != 200:
    fail(f"/version {status}")
version = expect_json(status, _headers, body, _elapsed)
digest = "c6676798e00bd9655bf3391f0c0f21dec100684d5c6783a6e0b2c3f8ae078c01"
names = version.get("packageSet")
if version.get("packageSetHash") != digest:
    fail(f"packageSetHash {version.get('packageSetHash')}")
for required in (
    "circuitikz",
    "pgfplots",
    "chemfig",
    "mhchem",
    "pgfgantt",
    "colophon-floorplan",
):
    if required not in names:
        fail(f"packageSet missing {required}")
print("packageSetHash", digest)

print("GET /load is not a worker path")
status, _headers, _body, _elapsed = request("GET", "/load", timeout=30)
if status != 404:
    fail(f"/load returned {status}")

print("GET /v1/host-load")
status, headers, body, _elapsed = request("GET", "/v1/host-load", timeout=30)
if status not in (200, 503):
    fail(f"/v1/host-load {status}")
if headers.get("Cache-Control") != "no-store":
    fail("host-load Cache-Control")
report = expect_json(status, headers, body, _elapsed)
expected = {"loadavg", "memAvailableMiB", "activeJobs", "queued", "reportedAt"}
if set(report) != expected:
    fail(f"host-load keys {sorted(report)}")
if not isinstance(report["activeJobs"], int) or report["activeJobs"] not in (0, 1):
    fail(f"activeJobs {report['activeJobs']!r}")
if report["queued"] != 0:
    fail(f"queued {report['queued']!r}")
if report["reportedAt"] is None:
    fail("reportedAt is null")
observed = datetime.fromisoformat(report["reportedAt"])
if observed.tzinfo is None or observed.utcoffset() != timedelta(0):
    fail(f"reportedAt {report['reportedAt']}")
print("host-load", {key: report[key] for key in ("loadavg", "memAvailableMiB", "activeJobs", "queued", "reportedAt")})

print("D5 write18 refused before compile")
for source in (
    "\\immediate\\write18{echo refused}",
    "\\write18{echo refused}",
):
    status, _headers, body, _elapsed = request("POST", "/v1/jobs", job(source))
    payload = expect_json(status, _headers, body, _elapsed)
    if status != 400 or payload.get("error") != "rejectInvalidInput":
        fail(f"write18 status {status} body {payload}")
    if payload.get("field") != "write18" or payload.get("result") != "refused":
        fail(f"write18 body {payload}")

print("small PDF")
status, _headers, body, _elapsed = request("POST", "/v1/jobs", job("Hello."))
if status != 200 or not body.startswith(b"%PDF"):
    fail(f"small pdf {status} {body[:120]!r}")
if len(body) > CAP:
    fail("small pdf exceeded the output cap")

print("smoke renders")
kind_dir = ROOT / "tests" / "colophon" / "fixtures" / "kinds"
for name in SMOKE:
    source = (kind_dir / name).read_text(encoding="utf-8")
    status, _headers, body, elapsed = request("POST", "/v1/jobs", job(source), timeout=90)
    if status != 200 or not body.startswith(b"%PDF"):
        fail(f"{name} {status} in {elapsed:.1f}s {body[:160]!r}")
    print(" ", name, len(body), "bytes", f"{elapsed:.1f}s")

print("D6 about 20 MiB passes")
status, _headers, body, elapsed = request(
    "POST", "/v1/jobs", job(expansion(UNDER_ITERS)), timeout=90
)
if status != 200 or not body.startswith(b"%PDF"):
    fail(f"under-cap {status} in {elapsed:.1f}s {body[:160]!r}")
if not (19 * 1024 * 1024 <= len(body) <= CAP):
    fail(f"under-cap size {len(body)} (want 19 MiB..20 MiB inclusive)")
print(" ", len(body), "bytes", f"{elapsed:.1f}s")

print("D6 just over 20 MiB is failCapHit")
status, _headers, body, elapsed = request(
    "POST", "/v1/jobs", job(expansion(OVER_ITERS)), timeout=90
)
payload = expect_json(status, _headers, body, elapsed)
if status != 413 or payload.get("error") != "failCapHit":
    fail(f"over-cap {status} {payload}")
if payload.get("result") != "failCapHit":
    fail(f"over-cap result {payload.get('result')}")
if "failOutputCap" in body.decode("utf-8", "replace"):
    fail("worker emitted failOutputCap")
print(" ", payload["error"], f"{elapsed:.1f}s")

print("D1 infinite loop is failTimeout in under 90 s")
status, _headers, body, elapsed = request(
    "POST",
    "/v1/jobs",
    job("\\loop\\iftrue\\relax\\repeat"),
    timeout=100,
)
payload = expect_json(status, _headers, body, elapsed)
if elapsed >= 90:
    fail(f"timeout took {elapsed:.1f}s")
if status != 408 or payload.get("error") != "failTimeout":
    fail(f"timeout {status} in {elapsed:.1f}s {payload}")
if payload.get("result") != "failTimeout":
    fail(f"timeout result {payload.get('result')}")
print(" ", f"{elapsed:.1f}s")

print("no leftover job container or TeX process")
listed = podman("ps", "-a", "--format", "{{.Names}}")
leftover = [
    line
    for line in listed.stdout.decode().splitlines()
    if line.startswith("colophon-job-")
]
if leftover:
    fail(f"leftover containers {leftover}")
for comm in ("xelatex", "xelatex-nonescape", "xdvipdfmx"):
    found = subprocess.run(["pgrep", "-x", comm], capture_output=True, check=False)
    if found.returncode == 0:
        fail(f"stray {comm}: {found.stdout.decode().strip()}")

print("D5 in-image write18 and Lua")
with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)
    proof = "/tmp/colophon-write18-proof"
    tex = work / "write18.tex"
    tex.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        f"\\immediate\\write18{{touch {proof}}}\n"
        "Hello.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    lua = work / "lua.tex"
    lua.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\directlua{\n"
        "  local exec = \"nil\"\n"
        "  if os ~= nil and os.execute ~= nil then\n"
        "    local ok = os.execute(\"echo OSEXEC > /tmp/colophon-osexec.txt\")\n"
        "    if ok == nil or ok == false then exec = \"refused\" else exec = \"ran\" end\n"
        "  end\n"
        "  local popen = \"nil\"\n"
        "  if io ~= nil and io.popen ~= nil then\n"
        "    local handle = io.popen(\"echo IOPOPEN\", \"r\")\n"
        "    if handle == nil then popen = \"refused\"\n"
        "    else\n"
        "      local data = handle:read(\"*a\") or \"\"\n"
        "      handle:close()\n"
        "      if string.find(data, \"IOPOPEN\", 1, true) then popen = \"ran\" else popen = \"refused\" end\n"
        "    end\n"
        "  end\n"
        "  texio.write_nl(\"COLOPHON_LUA exec=\" .. exec .. \" popen=\" .. popen)\n"
        "}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    work.chmod(0o755)
    for path in (tex, lua):
        path.chmod(0o644)
    script = (
        "set -eu; "
        f"/usr/local/bin/xelatex-nonescape -no-shell-escape -interaction=nonstopmode "
        f"-output-directory=/tmp /work/write18.tex >/tmp/xe.log 2>&1 || true; "
        f"if [ -e {proof} ]; then echo WRITE18_RAN; exit 1; fi; "
        "echo WRITE18_REFUSED; "
        "/usr/bin/lualatex -no-shell-escape -interaction=nonstopmode "
        "-output-directory=/tmp /work/lua.tex >/tmp/lua.log 2>&1 || true; "
        "if [ -e /tmp/colophon-osexec.txt ]; then echo LUA_RAN; exit 1; fi; "
        "grep -H COLOPHON_LUA /tmp/lua.log /tmp/lua.aux || true"
    )
    ran = podman(
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,size=512m,mode=1777",
        "--user",
        "10001:10001",
        "-v",
        f"{work}:/work:ro",
        "--entrypoint",
        "/bin/sh",
        IMAGE,
        "-c",
        script,
        check=False,
    )
    text = ran.stdout.decode("utf-8", "replace") + ran.stderr.decode("utf-8", "replace")
    if ran.returncode != 0 or "WRITE18_REFUSED" not in text:
        fail(f"in-image write18\n{text}")
    if "COLOPHON_LUA exec=ran" in text or "COLOPHON_LUA popen=ran" in text:
        fail(f"in-image lua ran\n{text}")
    if "COLOPHON_LUA exec=" not in text:
        fail(f"in-image lua report missing\n{text}")
    print(text.strip())

print("tmpfs above 512 MiB fails")
tmp_script = (
    "dd if=/dev/zero of=/tmp/small bs=1M count=1 status=none && "
    "if dd if=/dev/zero of=/tmp/big bs=1M count=513 status=none; then "
    "echo BIG_OK; else echo BIG_FAIL; fi"
)
ran = podman(
    "run",
    "--rm",
    "--network=none",
    "--read-only",
    "--tmpfs",
    "/tmp:rw,size=512m,mode=1777",
    "--user",
    "10001:10001",
    "--entrypoint",
    "/bin/sh",
    IMAGE,
    "-c",
    tmp_script,
    check=False,
)
text = ran.stdout.decode()
if ran.returncode != 0 or "BIG_FAIL" not in text or "BIG_OK" in text:
    fail(f"tmpfs {ran.returncode} {text!r} {ran.stderr.decode()!r}")
print("tmpfs BIG_FAIL")
print("ok")
PY
