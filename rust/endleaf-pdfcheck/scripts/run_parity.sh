#!/bin/sh
# Re-run every parity check. Usage (from the repo root):
#   rust/endleaf-pdfcheck/scripts/run_parity.sh PYTHON PYREF PDF_LIST WORKDIR
# PYTHON has the pinned pdfminer.six/shapely/scipy; PYREF is the reference driver
# (one in-process check_pdf per PDF with budgets lifted); PDF_LIST names the PDFs.
set -eu
PY=$1 PYREF=$2 LIST=$3 W=$4
HERE=$(dirname "$0")
BIN=${CARGO_TARGET_DIR:-$HERE/../target}/release/endleaf-pdfcheck
mkdir -p "$W"
"$PY" "$PYREF" . "$W/py-ref.json" $(cat "$LIST")
"$BIN" --page-budget 1e9 --doc-budget 1e9 $(cat "$LIST") > "$W/rust-out.jsonl"
"$PY" "$HERE/compare.py" "$W/py-ref.json" "$W/rust-out.jsonl"
"$PY" "$HERE/py_dump.py" . $(cat "$LIST") > "$W/py-dump.jsonl"
"$BIN" --dump --page-budget 1e9 --doc-budget 1e9 $(cat "$LIST") > "$W/rust-dump.jsonl"
"$PY" "$HERE/compare_dump.py" "$W/py-dump.jsonl" "$W/rust-dump.jsonl"
"$PY" "$HERE/synth_cases.py" . "$BIN" "$W/synth"
