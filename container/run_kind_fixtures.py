# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compile the sold-candidate kinds, plus a short smoke set.

The required set is the document shell and seven LaTeX diagram kinds: P&ID,
circuits, plots, chemistry, Gantt, floor plans, and SysML, plus the fulldoc
body. Mermaid and D2
are not rendered. Each remaining job reports job meters. Floor-plan PDFs
must show the same labels at scale=1 and scale=0.5. The SysML TeX fixture
must show the zh-TW label.

tikz-cd, forest, automata, mindmap, tikz-3dplot, tikz-feynman,
tikz-timing, and bytefield stay installed. Their smoke compiles are not
a sold kind. The TeX path is the server-owned template preamble plus the body.
The Markdown path is Pandoc plus the diagram filter.
"""

import argparse
import json
import re
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
    "document-shell.md",
    "floorplan-scale.md",
    "floorplan-scale.tex",
    "floorplan.md",
    "floorplan.tex",
    "fulldoc.tex",
    "gantt.md",
    "gantt.tex",
    "pgfplots.md",
    "pgfplots.tex",
    "pidcircuit.md",
    "pidcircuit.tex",
    "sysml.md",
    "sysml.tex",
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
        from colophon.cgroup_caps import CpuControllerMissing
        from colophon.podman_args import (
            build_podman_run_args,
            ensure_rlimit_hook_dir,
            podman_supports_ulimit_as,
            probe_podman_version,
        )

        version = probe_podman_version(podman)
        hooks_dir = None
        if not podman_supports_ulimit_as(version):
            hooks_dir = ensure_rlimit_hook_dir()
        try:
            args = build_podman_run_args(
                podman=podman,
                image=image,
                name=f"endleaf-kind-{uuid.uuid4().hex[:12]}",
                podman_version=version,
                hooks_dir=hooks_dir,
            )
        except CpuControllerMissing as exc:
            sys.exit(f"refusing to start: {exc}")
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


def _cjk_tokens_present(text, needle):
    """True when each needle glyph appears in order.

    pdftotext -raw may insert a newline or space between CJK characters.
    A missing or replaced glyph still fails.
    """
    pattern = r"\s*".join(re.escape(ch) for ch in needle)
    return re.search(pattern, text) is not None


_CREDIT = {
    "Creator": "Endleaf by InkMirage (endleaf.inkmirage.xyz)",
    "Producer": "Endleaf by InkMirage; XeTeX",
    "Keywords": "Endleaf",
}


def _pdf_fields(pdf):
    completed = subprocess.run(
        ["pdfinfo", "-"],
        input=pdf,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        sys.exit(completed.stderr.decode("utf-8", "replace") or "pdfinfo failed")
    fields = {}
    for line in completed.stdout.decode("utf-8", "replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _assert_credit(name, pdf):
    fields = _pdf_fields(pdf)
    for key, expected in _CREDIT.items():
        if fields.get(key) != expected:
            sys.exit(f"{name} {key} is {fields.get(key)!r}, expected {expected!r}")
    if "Subject" in fields:
        sys.exit(f"{name} set Subject {fields['Subject']!r}")


def _pdf_pages(pdf):
    completed = subprocess.run(
        ["pdfinfo", "-"],
        input=pdf,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        sys.exit(completed.stderr.decode("utf-8", "replace") or "pdfinfo failed")
    for line in completed.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    sys.exit("pdfinfo did not report Pages")


def _assert_fonts_embedded(name, pdf):
    path = Path("/tmp") / f"endleaf-fonts-{name}.pdf"
    path.write_bytes(pdf)
    try:
        completed = subprocess.run(
            ["pdffonts", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)
    if completed.returncode != 0:
        sys.exit(completed.stderr.decode("utf-8", "replace") or "pdffonts failed")
    lines = completed.stdout.decode("utf-8", "replace").splitlines()
    if len(lines) < 3 or "emb" not in lines[0]:
        sys.exit(f"{name} pdffonts output is unreadable: {lines!r}")
    rows = lines[2:]
    if not rows:
        sys.exit(f"{name} PDF has no fonts")
    for row in rows:
        # name and type vary in width. emb sub uni sit before the object id.
        if row.split()[-5] != "yes":
            sys.exit(f"{name} font is not embedded: {row}")
    blob = "\n".join(rows).lower().replace("-", "").replace(" ", "")
    for banned in ("cmr", "lmroman", "latinmodernroman"):
        if banned in blob:
            sys.exit(
                f"{name} PDF still uses Computer Modern or Latin Modern Roman:\n"
                + "\n".join(lines)
            )
    if "pagella" not in blob:
        sys.exit(
            f"{name} PDF body is not TeX Gyre Pagella:\n" + "\n".join(lines)
        )


def _assert_fulldoc(name, pdf, err):
    if "ENDLEAF_OVERFULL 0" not in err:
        sys.exit(f"{name} expected no Overfull hbox\n{err[-2000:]}")
    pages = _pdf_pages(pdf)
    if pages < 1 or pages > 16:
        sys.exit(f"{name} page count {pages} is outside 1..16")
    text = _pdf_text(pdf)
    for needle in ("幫浦", "參數", "配置"):
        if not _cjk_tokens_present(text, needle):
            sys.exit(f"{name} PDF text missing {needle}: {text!r}")
    # Captions number on the first pass. ?? is an unresolved \ref.
    if "??" in text or not re.search(r"圖\s*1", text) or not re.search(r"表\s*1", text):
        sys.exit(f"{name} PDF cross-references are unresolved: {text!r}")
    _assert_fonts_embedded(name, pdf)


def _assert_floorplan(name, pdf):
    text = _pdf_text(pdf)
    missing = [needle for needle in FLOORPLAN_NEEDLES if needle not in text]
    if missing:
        sys.exit(f"{name} PDF text missing {missing}: {text!r}")


def _template_id(path):
    if path.suffix == ".md" or path.stem == "document-shell":
        return "document-shell"
    if path.stem in ("pgfplots",):
        return "plots"
    if path.stem in ("floorplan", "floorplan-scale"):
        return "floorplan"
    if path.stem == "sysml":
        return "sysml"
    if path.stem == "fulldoc":
        return "fulldoc"
    if path.stem in ("chemistry", "circuits", "gantt", "pidcircuit"):
        return path.stem
    # Unsold smoke files use a TeX template whose preamble inputs the
    # full allowlist, so tikz-cd and the other installed packages resolve.
    return "gantt"


def _compile(path, *, image, podman):
    code, stdout, stderr = _render(
        {
            "body": path.read_text(encoding="utf-8"),
            "templateId": _template_id(path),
            "outputFormat": "pdf",
            "lane": "Weft",
        },
        image=image,
        podman=podman,
    )
    err = stderr.decode("utf-8", "replace")
    if code != 0 or not stdout.startswith(b"%PDF") or "ENDLEAF_STATUS ok" not in err:
        sys.exit(f"{path.name} failed rc={code}\n{err[-4000:]}")
    if "ENDLEAF_METERS " not in err:
        sys.exit(f"{path.name} did not report cgroup meters")
    _assert_credit(path.name, stdout)
    if path.stem.startswith("floorplan"):
        _assert_floorplan(path.name, stdout)
    if path.name == "sysml.tex":
        text = _pdf_text(stdout)
        if not _cjk_tokens_present(text, "幫浦"):
            sys.exit(f"{path.name} PDF text missing 幫浦: {text!r}")
    if path.name == "fulldoc.tex":
        _assert_fulldoc(path.name, stdout, err)
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
