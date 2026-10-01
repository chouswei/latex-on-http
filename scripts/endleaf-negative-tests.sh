#!/bin/sh
# Live checks for a running Endleaf by Inkmirage worker. Devicor runs this on the Pi.
#
# After a live PDF render, pdffonts should list TeX Gyre Pagella, Heros,
# and Cursor, not Computer Modern (CMR) for body type. The image installs
# Debian tex-gyre for that stack (see README, Type stack).
#
#   ENDLEAF_URL=http://100.64.0.1:8080 \
#   ENDLEAF_WORKER_TOKEN=... \
#   ENDLEAF_IMAGE=localhost/endleaf-render:local \
#   scripts/endleaf-negative-tests.sh
#
# ENDLEAF_PODMAN defaults to podman.
# COLOPHON_URL, COLOPHON_WORKER_TOKEN, COLOPHON_IMAGE, and COLOPHON_PODMAN
# are still read when the ENDLEAF_* name is unset. Each use logs one line.
# The output-cap token is failCapHit (HTTP 413). The worker does not emit
# failOutputCap.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
export ENDLEAF_ROOT="$ROOT"
if [ -z "${ENDLEAF_URL:-}" ] && [ -n "${COLOPHON_URL:-}" ]; then
  echo "deprecated environment variable COLOPHON_URL; set ENDLEAF_URL" >&2
  ENDLEAF_URL=$COLOPHON_URL
fi
if [ -z "${ENDLEAF_WORKER_TOKEN:-}" ] && [ -n "${COLOPHON_WORKER_TOKEN:-}" ]; then
  echo "deprecated environment variable COLOPHON_WORKER_TOKEN; set ENDLEAF_WORKER_TOKEN" >&2
  ENDLEAF_WORKER_TOKEN=$COLOPHON_WORKER_TOKEN
fi
if [ -z "${ENDLEAF_IMAGE:-}" ] && [ -n "${COLOPHON_IMAGE:-}" ]; then
  echo "deprecated environment variable COLOPHON_IMAGE; set ENDLEAF_IMAGE" >&2
  ENDLEAF_IMAGE=$COLOPHON_IMAGE
fi
if [ -z "${ENDLEAF_PODMAN:-}" ] && [ -n "${COLOPHON_PODMAN:-}" ]; then
  echo "deprecated environment variable COLOPHON_PODMAN; set ENDLEAF_PODMAN" >&2
  ENDLEAF_PODMAN=$COLOPHON_PODMAN
fi
: "${ENDLEAF_URL:?set ENDLEAF_URL}"
: "${ENDLEAF_WORKER_TOKEN:?set ENDLEAF_WORKER_TOKEN}"
: "${ENDLEAF_IMAGE:?set ENDLEAF_IMAGE}"
export ENDLEAF_URL ENDLEAF_WORKER_TOKEN ENDLEAF_IMAGE
export ENDLEAF_PODMAN="${ENDLEAF_PODMAN:-podman}"
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
BASE = os.environ["ENDLEAF_URL"].rstrip("/")
TOKEN = os.environ["ENDLEAF_WORKER_TOKEN"]
IMAGE = os.environ["ENDLEAF_IMAGE"]
PODMAN = os.environ["ENDLEAF_PODMAN"]
CAP = 20 * 1024 * 1024
# XeLaTeX has no \pdfcompresslevel or \pdfobjcompresslevel. dvipdfmx
# config z 0 is the equivalent: streams are stored uncompressed.
# The page is 50 words of 40 B's (2000 letters) so TeX can break the
# line. One unbroken line of that length makes XeTeX hang in the line
# breaker. 3000 such pages measured 27294403 bytes on TeX Live 2023
# (about 2.3 s). That is over the 20 MiB cap, and each page is shipped
# out so TeX main memory is not exhausted.
PAGE_COUNT = 3000
CHARS_PER_PAGE = 2000
WORDS_PER_PAGE = 50
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


SMOKE_TEMPLATE = {
    "circuits.tex": "circuits",
    "pgfplots.tex": "plots",
    "chemistry.tex": "chemistry",
    "gantt.tex": "gantt",
    "floorplan.tex": "floorplan",
    "pidcircuit.tex": "pidcircuit",
}


def job(source, template="gantt"):
    return {
        "body": source,
        "templateId": template,
        "outputFormat": "pdf",
        "lane": "InstruMeasure",
    }


def expect_json(status, headers, body, elapsed):
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"expected JSON, got {status} {body[:200]!r} ({exc})")


def multipage(pages=PAGE_COUNT):
    word = "B" * (CHARS_PER_PAGE // WORDS_PER_PAGE)
    paragraph = " ".join([word] * WORDS_PER_PAGE)
    return (
        "\\special{dvipdfmx:config z 0}\n"
        "\\newcount\\i\n"
        "\\loop\n"
        f"\\ifnum\\i<{pages}\n"
        "  \\advance\\i by 1\n"
        f"{paragraph}\\par\n"
        "  \\newpage\n"
        "\\repeat\n"
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
digest = "f2946ed8f9682cc0e0dffa468d29fdc25ae2feb85e7d9d1291414dc1cf2a310d"
names = version.get("packageSet")
if version.get("packageSetHash") != digest:
    fail(f"packageSetHash {version.get('packageSetHash')}")
for required in (
    "circuitikz",
    "pgfplots",
    "chemfig",
    "mhchem",
    "pgfgantt",
    "endleaf-floorplan",
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
expected = {
    "loadAvg1m",
    "memAvailableMiB",
    "busy",
    "stale",
    "intervalSec",
    "readable",
    "reportedAt",
}
if set(report) != expected:
    fail(f"host-load keys {sorted(report)}")
if status == 503:
    if report["readable"] is not False or report["stale"] is not True:
        fail(f"unreadable host-load {report}")
else:
    if report["readable"] is not True:
        fail(f"readable host-load {report}")
    if not isinstance(report["loadAvg1m"], (int, float)) or isinstance(report["loadAvg1m"], bool):
        fail(f"loadAvg1m {report['loadAvg1m']!r}")
if not isinstance(report["busy"], bool) or not isinstance(report["stale"], bool):
    fail(f"host-load flags {report}")
if report["intervalSec"] != 10:
    fail(f"intervalSec {report['intervalSec']!r}")
if report["reportedAt"] is None:
    fail("reportedAt is null")
observed = datetime.fromisoformat(report["reportedAt"])
if observed.tzinfo is None or observed.utcoffset() != timedelta(0):
    fail(f"reportedAt {report['reportedAt']}")
print("host-load", report)

print("POST /v1/jobs/abort")
status, _headers, body, _elapsed = request("POST", "/v1/jobs/abort", timeout=30)
payload = expect_json(status, _headers, body, _elapsed)
if status != 404 or payload.get("aborted") is not False or payload.get("error") != "idle":
    fail(f"idle abort {status} {payload}")

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

print("D5 lualatex cannot be selected")
for path, payload_in in (
    (
        "/v1/jobs",
        {**job("Hello."), "compiler": "lualatex"},
    ),
    (
        "/builds/sync",
        {
            "compiler": "lualatex",
            "lane": "InstruMeasure",
            "outputFormat": "pdf",
            "inputKind": "tex",
            "resources": [{"main": True, "content": "Hello."}],
        },
    ),
):
    status, _headers, body, _elapsed = request("POST", path, payload_in)
    payload = expect_json(status, _headers, body, _elapsed)
    if status != 400 or payload.get("error") != "rejectInvalidInput":
        fail(f"lualatex {path} {status} {payload}")
    if payload.get("field") != "compiler":
        fail(f"lualatex field {payload}")

print("D5 directlua is refused")
status, _headers, body, _elapsed = request(
    "POST", "/v1/jobs", job("\\directlua{os.execute([[echo PWNED]])}")
)
payload = expect_json(status, _headers, body, _elapsed)
if status != 400 or payload.get("error") != "rejectInvalidInput":
    fail(f"directlua {status} {payload}")
if payload.get("field") != "directlua":
    fail(f"directlua field {payload}")

print("documentclass is refused")
status, _headers, body, _elapsed = request(
    "POST",
    "/v1/jobs",
    job("\\documentclass{article}\nHello."),
)
payload = expect_json(status, _headers, body, _elapsed)
if status != 400 or payload.get("field") != "documentclass":
    fail(f"documentclass {status} {payload}")
if payload.get("error") != "rejectInvalidInput":
    fail(f"documentclass error {payload}")

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
    status, _headers, body, elapsed = request(
        "POST", "/v1/jobs", job(source, SMOKE_TEMPLATE[name]), timeout=90
    )
    if status != 200 or not body.startswith(b"%PDF"):
        fail(f"{name} {status} in {elapsed:.1f}s {body[:160]!r}")
    print(" ", name, len(body), "bytes", f"{elapsed:.1f}s")

print("D6 3000 uncompressed pages is failCapHit")
status, _headers, body, elapsed = request(
    "POST", "/v1/jobs", job(multipage()), timeout=90
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
    if line.startswith("endleaf-job-")
]
if leftover:
    fail(f"leftover containers {leftover}")
for comm in ("xelatex", "xelatex-nonescape", "xdvipdfmx"):
    found = subprocess.run(["pgrep", "-x", comm], capture_output=True, check=False)
    if found.returncode == 0:
        fail(f"stray {comm}: {found.stdout.decode().strip()}")

print("D5 sandbox shell-escape, write18, and lualatex")
with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)
    tex = work / "write18.tex"
    tex.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\immediate\\write18{touch /tmp/x}\n"
        "Hello.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    lua = work / "lua.tex"
    lua.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\directlua{\n"
        "  texio.write_nl(\"ENDLEAF_LUA_RAN\")\n"
        "  local exec_fn = nil\n"
        "  if os ~= nil then exec_fn = os.execute end\n"
        "  local popen_fn = nil\n"
        "  if io ~= nil then popen_fn = io.popen end\n"
        "  texio.write_nl(\"ENDLEAF_LUA type_execute=\" .. type(exec_fn))\n"
        "  texio.write_nl(\"ENDLEAF_LUA type_popen=\" .. type(popen_fn))\n"
        "  local ok1, r1 = pcall(exec_fn, \"touch /tmp/x-lua\")\n"
        "  texio.write_nl(\"ENDLEAF_LUA pcall_execute=\" .. tostring(ok1) .. \":\" .. tostring(r1))\n"
        "  local ok2, r2 = pcall(popen_fn, \"echo IOPOPEN\")\n"
        "  texio.write_nl(\"ENDLEAF_LUA pcall_popen=\" .. tostring(ok2) .. \":\" .. tostring(r2))\n"
        "}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    work.chmod(0o755)
    for path in (tex, lua):
        path.chmod(0o644)
    script = r"""
set -eu
escape=$(kpsewhich -var-value shell_escape)
echo "shell_escape=${escape}"
case "$escape" in
  f) ;;
  *) echo "shell_escape is not f"; exit 1 ;;
esac
rm -f /tmp/x /tmp/x-lua
# /work is a read-only mount. openin_any=p refuses that absolute path.
# Copy the sources into the tmpfs and compile the basename from /tmp.
cp /work/write18.tex /tmp/write18.tex
cp /work/lua.tex /tmp/lua.tex
cd /tmp
/usr/local/bin/xelatex-nonescape -interaction=nonstopmode -cnf-line=openin_any=p write18.tex >/tmp/xe.out 2>&1 || true
if grep -q 'Not reading' /tmp/xe.out /tmp/write18.log 2>/dev/null; then echo OPENIN_REFUSED engine=xelatex; exit 1; fi
if [ ! -s /tmp/write18.pdf ]; then echo XELATEX_DID_NOT_COMPILE; exit 1; fi
if [ -e /tmp/x ]; then echo WRITE18_EXISTS engine=xelatex; exit 1; fi
echo "WRITE18_ABSENT engine=xelatex"
if [ -x /usr/local/bin/pdflatex ]; then
  rm -f /tmp/x /tmp/write18.pdf
  /usr/local/bin/pdflatex -interaction=nonstopmode -cnf-line=openin_any=p write18.tex >/tmp/pdf.out 2>&1 || true
  if grep -q 'Not reading' /tmp/pdf.out /tmp/write18.log 2>/dev/null; then echo OPENIN_REFUSED engine=pdflatex-wrapper; exit 1; fi
  if [ ! -s /tmp/write18.pdf ]; then echo PDFLATEX_DID_NOT_COMPILE; exit 1; fi
  if [ -e /tmp/x ]; then echo WRITE18_EXISTS engine=pdflatex-wrapper; exit 1; fi
  echo "PDFLATEX_IS_XELATEX_WRAPPER"
  echo "WRITE18_ABSENT engine=pdflatex-wrapper"
fi
if ! command -v lualatex >/dev/null 2>&1; then
  echo "LUALATEX_REFUSED lualatex is not installed in the worker image"
  exit 0
fi
/usr/bin/lualatex -no-shell-escape -interaction=nonstopmode -cnf-line=openin_any=p lua.tex >/tmp/lua.out 2>&1 || true
if grep -q 'Not reading' /tmp/lua.out /tmp/lua.log 2>/dev/null; then echo OPENIN_REFUSED engine=lualatex; exit 1; fi
if [ -e /tmp/x-lua ]; then echo LUA_SIDE_EFFECT; exit 1; fi
if grep -q ENDLEAF_LUA_RAN /tmp/lua.log /tmp/lua.out /tmp/lua.aux 2>/dev/null; then
  grep -h ENDLEAF_LUA /tmp/lua.log /tmp/lua.out /tmp/lua.aux
  exit 0
fi
echo "LUALATEX_REFUSED lualatex is not available in the worker"
grep -m 6 -E '^!|format|not found|I can' /tmp/lua.log /tmp/lua.out || true
"""
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
    if ran.returncode != 0:
        fail(f"sandbox shell check\n{text}")
    if "shell_escape=f" not in text:
        fail(f"shell_escape\n{text}")
    if "WRITE18_ABSENT engine=xelatex" not in text or "WRITE18_EXISTS" in text:
        fail(f"write18\n{text}")
    if "ENDLEAF_LUA_RAN" in text:
        ran_at = text.find("ENDLEAF_LUA_RAN")
        for needle in (
            "ENDLEAF_LUA type_execute=",
            "ENDLEAF_LUA type_popen=",
            "ENDLEAF_LUA pcall_execute=",
            "ENDLEAF_LUA pcall_popen=",
        ):
            at = text.find(needle)
            if at < ran_at:
                fail(f"lua marker order\n{text}")
        if "LUA_SIDE_EFFECT" in text:
            fail(f"lua side effect\n{text}")
        print("lualatex positive control:")
        for line in text.splitlines():
            if "ENDLEAF_LUA" in line:
                print(" ", line.strip())
    elif "LUALATEX_REFUSED" in text:
        print("lualatex is not available in the worker:")
        for line in text.splitlines():
            if "LUALATEX_REFUSED" in line or line.startswith("!"):
                print(" ", line.strip())
    else:
        fail(f"lua report missing\n{text}")
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
