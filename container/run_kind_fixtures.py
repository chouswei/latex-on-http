# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compile one Markdown fence and one TeX body per engine kind.

The TeX path is the lane wrapper. The Markdown path is Pandoc plus the
diagram filter. Both go through colophon-sandbox-render. Floor-plan PDFs
must show the same labels at scale=1 and scale=0.5.
"""

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

FLOORPLAN_NEEDLES = ("2.00 m", "1.50 m", "3 m2", "2.25 m2")


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--image", default="")
    parser.add_argument("--podman", default="podman")
    args = parser.parse_args()
    root = args.root or (_repo_root() / "tests" / "colophon" / "fixtures" / "kinds")
    files = sorted(path for path in root.iterdir() if path.suffix in {".tex", ".md"})
    if not files:
        sys.exit(f"no kind fixtures in {root}")
    seen = {path.stem for path in files}
    for kind in (
        "circuitikz",
        "siunitx",
        "pgfplots",
        "chemfig",
        "mhchem",
        "tikz-3dplot",
        "tikz-feynman",
        "tikz-cd",
        "forest",
        "tikz-timing",
        "bytefield",
        "pgfgantt",
        "tikz-dimline",
        "tikzscale",
        "colophon-floorplan",
    ):
        if f"{kind}.tex" not in {path.name for path in files}:
            sys.exit(f"missing {kind}.tex")
        if f"{kind}.md" not in {path.name for path in files}:
            sys.exit(f"missing {kind}.md")
    if "mermaid.md" not in seen and "mermaid" not in {p.stem for p in files}:
        sys.exit("missing mermaid.md")
    for path in files:
        kind = "markdown" if path.suffix == ".md" else "tex"
        code, stdout, stderr = _render(
            {
                "input": path.read_text(encoding="utf-8"),
                "inputKind": kind,
                "outputFormat": "pdf",
                "lane": "Weft",
            },
            image=args.image or None,
            podman=args.podman,
        )
        err = stderr.decode("utf-8", "replace")
        if code != 0 or not stdout.startswith(b"%PDF") or "COLOPHON_STATUS ok" not in err:
            sys.exit(f"{path.name} failed rc={code}\n{err[-4000:]}")
        if "COLOPHON_METERS " not in err:
            sys.exit(f"{path.name} did not report cgroup meters")
        if path.stem.startswith("colophon-floorplan"):
            _assert_floorplan(path.name, stdout)
        print(path.name, "ok", len(stdout))


if __name__ == "__main__":
    main()
