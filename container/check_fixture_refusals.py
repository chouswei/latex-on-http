# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Image-build check: negative fixtures are refused before TeX runs."""

import sys
from pathlib import Path

from colophon.enums import JobRejected
from colophon.source_policy import reject_forbidden_source

ROOT = Path("/tmp/colophon-fixtures")
EXPECT = {
    "reject-shell-escape.tex": "write18",
    "reject-minted.tex": "minted",
    "reject-tikz-external.tex": "tikz-external",
    "reject-asymptote.tex": "asymptote",
    "reject-gnuplot.tex": "gnuplot",
    "reject-epstopdf.tex": "epstopdf",
    "reject-svg.tex": "svg",
    "reject-feynman-auto.tex": "feynman-auto",
    "reject-mermaid.md": "mermaid",
    "reject-d2.md": "d2",
}


def main():
    for name, reason in EXPECT.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        try:
            reject_forbidden_source(text)
        except JobRejected as exc:
            if exc.reason != reason:
                sys.exit(f"{name} refused as {exc.reason}, expected {reason}")
        else:
            sys.exit(f"{name} was not refused")
    allowed = (ROOT / "packages-once.tex").read_text(encoding="utf-8")
    try:
        reject_forbidden_source(allowed)
    except JobRejected as exc:
        sys.exit(f"packages-once.tex refused as {exc.reason}")


if __name__ == "__main__":
    main()
