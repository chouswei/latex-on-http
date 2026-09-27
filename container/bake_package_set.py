# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Write the Endleaf TeX package set into the image. Build time only."""

import subprocess
import sys
from pathlib import Path

ROOT = Path("/opt/colophon/colophon")
SOURCE = ROOT / "package_set.txt"
DEST = ROOT / "PACKAGE_SET"


def main():
    names = [
        line.strip()
        for line in SOURCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if names != sorted(set(names)):
        sys.exit("package_set.txt must be sorted and unique")
    for name in names:
        found = subprocess.run(
            ["kpsewhich", f"{name}.sty"],
            capture_output=True,
            text=True,
            check=False,
        )
        if found.returncode != 0 or not found.stdout.strip():
            sys.exit(f"missing {name}.sty")
    DEST.write_text("\n".join(names) + "\n", encoding="utf-8")
    DEST.chmod(0o444)


if __name__ == "__main__":
    main()
