# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R82. Shared helpers for the endleaf-pdfcheck tests (not a test module).

The binary is found in this order: ``ENDLEAF_PDFCHECK_BIN``, ``$CARGO_TARGET_DIR/release``,
``rust/endleaf-pdfcheck/target/release``, then ``endleaf-pdfcheck`` on PATH. Build it with
``cargo build --release --locked --manifest-path rust/endleaf-pdfcheck/Cargo.toml``.
With ``ENDLEAF_PDFCHECK_REQUIRED=1`` (the CI parity job) a missing binary or missing
pinned oracle libraries fail the test instead of skipping it.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CRATE = ROOT / "rust/endleaf-pdfcheck"
REAL = ROOT / "tests/fixtures/pdfcheck-real"
GAP = CRATE / "tests/fixtures/gap"
CORPUS_LIST = CRATE / "corpus.txt"
ORACLE_REQUIREMENTS = ROOT / "tests/requirements-pdfcheck-oracle.txt"
LIFTED = ["--page-budget", "1e9", "--doc-budget", "1e9"]


def required():
    return os.environ.get("ENDLEAF_PDFCHECK_REQUIRED") == "1"


def missing(reason):
    """Skip, or fail when the run must have the binary and the oracle (CI parity job)."""
    if required():
        pytest.fail(reason + " (ENDLEAF_PDFCHECK_REQUIRED=1)")
    pytest.skip(reason)


def find_binary():
    named = os.environ.get("ENDLEAF_PDFCHECK_BIN")
    if named:
        return named
    candidates = []
    if os.environ.get("CARGO_TARGET_DIR"):
        candidates.append(
            Path(os.environ["CARGO_TARGET_DIR"]) / "release/endleaf-pdfcheck"
        )
    candidates.append(CRATE / "target/release/endleaf-pdfcheck")
    on_path = shutil.which("endleaf-pdfcheck")
    if on_path:
        candidates.append(Path(on_path))
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def binary_or_skip():
    path = find_binary()
    if path is None:
        missing("endleaf-pdfcheck is not built")
    return path


def oracle_pins():
    """``{distribution: version}`` of the four checker libraries pinned for the oracle."""
    text = ORACLE_REQUIREMENTS.read_text(encoding="utf-8")
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", text, re.MULTILINE))
    return {name: pins[name] for name in ("pdfminer-six", "shapely", "scipy", "numpy")}


def oracle_or_skip():
    """The reference oracle module, only with the exact pinned libraries installed."""
    from importlib.metadata import PackageNotFoundError, version

    for name, pinned in oracle_pins().items():
        try:
            found = version(name)
        except PackageNotFoundError:
            missing(f"oracle library {name} is not installed")
        if found != pinned:
            missing(f"oracle library {name} is {found}, the oracle pins {pinned}")
    from colophon import pdf_layout_check

    return pdf_layout_check


def run_sidecar(binary, sidecar, pdf_path, tmp_path, lifted=True):
    """``{items, log}`` of one ``--sidecar`` run (budgets lifted by default)."""
    side = Path(tmp_path) / (Path(pdf_path).stem + ".sidecar.json")
    side.write_text(json.dumps(sidecar), encoding="utf-8")
    command = [
        binary,
        *(LIFTED if lifted else []),
        "--sidecar",
        str(side),
        str(pdf_path),
    ]
    done = subprocess.run(command, capture_output=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-1500:]
    return json.loads(done.stdout)


def real_samples():
    return sorted(p.name for p in REAL.iterdir() if (p / "out.pdf").is_file())


def oracle_kwargs(sidecar):
    """check_pdf keyword arguments for an R82-IFACE sidecar (as sandbox_render built them)."""
    return {
        "template_id": sidecar.get("templateId", ""),
        "blocks": {int(k): tuple(v) for k, v in sidecar.get("blocks", {}).items()},
        "marks": [list(row) for row in sidecar.get("marks", [])] or None,
        "shell_pages": {int(k): v for k, v in sidecar.get("shellPages", {}).items()}
        or None,
        "tex_pages": set(sidecar.get("texPages", [])),
    }


ITEM_FIELDS = (
    "code",
    "packages",
    "message",
    "page",
    "regionCount",
    "overMm",
    "partId",
    "fenceNumber",
    "count",
)


def item_diffs(expected, actual, tolerance=0.5):
    """Differences between two item lists (R82-PARITY fields, box edges within ``tolerance`` pt)."""
    out = []
    if len(expected) != len(actual):
        out.append(f"{len(expected)} items != {len(actual)} items")
    for n, (a, b) in enumerate(zip(expected, actual)):
        if set(a) != set(b):
            out.append(f"item {n}: keys {sorted(a)} != {sorted(b)}")
        for key in ITEM_FIELDS:
            if a.get(key) != b.get(key):
                out.append(f"item {n}: {key} {a.get(key)!r} != {b.get(key)!r}")
        box_a, box_b = a.get("box"), b.get("box")
        if (box_a is None) != (box_b is None) or (
            box_a is not None
            and (
                len(box_a) != 4
                or len(box_b) != 4
                or any(abs(x - y) > tolerance for x, y in zip(box_a, box_b))
            )
        ):
            out.append(f"item {n}: box {box_a} != {box_b}")
    return out


def log_from_sidecar(sidecar):
    """A TeX log whose ENDLEAF lines and overfull rows give back this sidecar.

    Use with ``body_start=1, body_lines=10``: each ``texPages`` page gets one overfull row
    (job.tex line 3) shipped out on that page.
    """
    lines = []
    for page, (left, top, width, height) in sorted(
        sidecar["blocks"].items(), key=lambda kv: int(kv[0])
    ):
        lines.append(f"ENDLEAF_PAGEBLOCK {page} {left}pt {top}pt {width}pt {height}pt")
    for ident, tag, page, y_pt, orientation in sidecar.get("marks", []):
        turned = "landscape" if orientation == "l" else "portrait"
        lines.append(
            f"ENDLEAF_MARK {ident} {tag} {page} {round(y_pt * 65536)} {turned}"
        )
    for number, page in sorted(
        sidecar["shellPages"].items(), key=lambda kv: int(kv[0])
    ):
        lines.append(f"ENDLEAF_SHELLPAGE {number} {page} portrait")
    last = max([int(p) for p in sidecar["blocks"]] + list(sidecar["texPages"]) + [1])
    for page in range(1, last + 1):
        if page in sidecar["texPages"]:
            lines.append("Overfull \\hbox (30.0pt too wide) in paragraph at lines 3--4")
            lines.append(" []")
            lines.append("")
        lines.append(f"[{page}]")
    return "\n".join(lines) + "\n"
