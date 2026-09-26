# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compile the sold-candidate kinds, plus a short smoke set.

The required set is the document shell and eight diagram kinds: Mermaid,
D2, P&ID, circuits, plots, chemistry, Gantt, and floor plans. Each job
reports cgroup meters. Floor-plan PDFs must show the same labels at
scale=1 and scale=0.5.

tikz-cd, forest, automata, mindmap, tikz-3dplot, tikz-feynman,
tikz-timing, and bytefield stay installed. Their smoke compiles are not
a sold kind. The TeX path is the lane wrapper. The Markdown path is
Pandoc plus the diagram filter.
"""

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

FLOORPLAN_NEEDLES = ("2.00 m", "1.50 m", "3 m2", "2.25 m2")

REQUIRED = (
    "chemistry.md",
    "chemistry.tex",
    "circuits.md",
    "circuits.tex",
    "d2.md",
    "document-shell.md",
    "floorplan-scale.md",
    "floorplan-scale.tex",
    "floorplan.md",
    "floorplan.tex",
    "gantt.md",
    "gantt.tex",
    "mermaid.md",
    "pgfplots.md",
    "pgfplots.tex",
    "pidcircuit.md",
    "pidcircuit.tex",
)

SMOKE = (
    "automata.tex",
    "bytefield.tex",
    "forest.tex",
    "mindmap.tex",
    "tikz-3dplot.tex",
    "tikz-cd.tex",
    "tikz-feynman.tex",
    "tikz-timing.tex",
)


def _repo_root():
    return Path(__file__).resolve().parents[1]


def _render(payload, *, image, podman):
    raw = json.dumps(payload).encode("utf-8")
    if image:
        from colophon.podman_args import build_podman_run_args

        args = build_podman_run_args(
            podman=podman,
            image=image,
            name=f"colophon-kind-{uuid.uuid4().hex[:12]}",
        )
    else:
        args = [sys.executable, "-m", "colophon.sandbox_render"]
    completed = subprocess.run(
        args,
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _pdf_text(pdf):
    completed = subprocess.run(
        ["pdftotext", "-raw", "-", "-"],
        input=pdf,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        sys.exit(completed.stderr.decode("utf-8", "replace") or "pdftotext failed")
    text = completed.stdout.decode("utf-8", "replace")
    return text.replace("m²", "m2").replace("m^2", "m2")


def _assert_floorplan(name, pdf):
    text = _pdf_text(pdf)
    missing = [needle for needle in FLOORPLAN_NEEDLES if needle not in text]
    if missing:
        sys.exit(f"{name} PDF text missing {missing}: {text!r}")


def _compile(path, *, image, podman):
    kind = "markdown" if path.suffix == ".md" else "tex"
    code, stdout, stderr = _render(
        {
            "input": path.read_text(encoding="utf-8"),
            "inputKind": kind,
            "outputFormat": "pdf",
            "lane": "Weft",
        },
        image=image,
        podman=podman,
    )
    err = stderr.decode("utf-8", "replace")
    if code != 0 or not stdout.startswith(b"%PDF") or "COLOPHON_STATUS ok" not in err:
        sys.exit(f"{path.name} failed rc={code}\n{err[-4000:]}")
    if "COLOPHON_METERS " not in err:
        sys.exit(f"{path.name} did not report cgroup meters")
    if path.stem.startswith("floorplan"):
        _assert_floorplan(path.name, stdout)
    print(path.name, "ok", len(stdout))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--image", default="")
    parser.add_argument("--podman", default="podman")
    args = parser.parse_args()
    root = args.root or (_repo_root() / "tests" / "colophon" / "fixtures" / "kinds")
    files = sorted(path for path in root.iterdir() if path.suffix in {".tex", ".md"})
    found = tuple(path.name for path in files)
    if found != REQUIRED:
        sys.exit(f"required kind set mismatch: {found}")
    smoke_root = root.parent / "smoke"
    smoke = sorted(smoke_root.glob("*.tex"))
    if tuple(path.name for path in smoke) != SMOKE:
        sys.exit(f"smoke set mismatch: {[path.name for path in smoke]}")
    image = args.image or None
    for path in files:
        _compile(path, image=image, podman=args.podman)
    for path in smoke:
        _compile(path, image=image, podman=args.podman)


if __name__ == "__main__":
    main()
