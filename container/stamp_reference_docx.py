#!/usr/bin/env python3
"""Copy a pandoc reference.docx and set dc:title to the lane name."""

import sys
import zipfile
from pathlib import Path


def stamp(src, dest, lane):
    source = Path(src)
    target = Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as zin:
        try:
            core = zin.read("docProps/core.xml").decode("utf-8")
        except KeyError as exc:
            raise SystemExit("reference.docx has no docProps/core.xml") from exc
        if "<dc:title>" not in core or "</dc:title>" not in core:
            raise SystemExit("reference.docx core.xml has no dc:title")
        start = core.index("<dc:title>") + len("<dc:title>")
        end = core.index("</dc:title>")
        core = core[:start] + lane + core[end:]
        with zipfile.ZipFile(target, "w") as zout:
            for info in zin.infolist():
                data = (
                    core.encode("utf-8")
                    if info.filename == "docProps/core.xml"
                    else zin.read(info.filename)
                )
                zout.writestr(info, data)


def main(argv):
    if len(argv) != 4:
        raise SystemExit("usage: stamp_reference_docx.py SRC DEST LANE")
    stamp(argv[1], argv[2], argv[3])


if __name__ == "__main__":
    main(sys.argv)
