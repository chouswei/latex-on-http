# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""openin_any=p must still compile. TeX sees a relative name or a kpathsea name."""

import base64
import io
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from colophon.render_plan import RenderPlanError, xelatex_argv
from colophon.sandbox_render import render_to_stdout

_ROOT = Path(__file__).resolve().parents[2]
_TEXINPUTS = os.pathsep.join(
    (
        str(_ROOT / "colophon/share/tex/latex/colophon-v1"),
        str(_ROOT / "colophon/share/tex/latex/endleaf-floorplan"),
        str(_ROOT / "colophon/share/tex/latex/sysml-tikz"),
        str(_ROOT / "vendor/pidcircuittikz"),
        "",
    )
)
_XELATEX = shutil.which("xelatex")
_PANDOC = shutil.which("pandoc")
_PDFTOTEXT = shutil.which("pdftotext")
_INKSCAPE = shutil.which("inkscape")
_ABS_INPUT = re.compile(
    r"\\(?:input|include|usepackage|RequirePackage)\s*(?:\[[^\]]*\]\s*)?\{([^}]*)\}"
)
_FENCE = (
    "A labelled pump.\n\n"
    "```tikz\n"
    "\\begin{circuitikz}\n"
    "  \\draw (0,0) to[R, l=幫浦] (3,0);\n"
    "\\end{circuitikz}\n"
    "```\n"
)


def _pandoc_major():
    if _PANDOC is None:
        return 0
    completed = subprocess.run(
        [_PANDOC, "-v"],
        check=False,
        capture_output=True,
        text=True,
    )
    match = re.match(r"pandoc (\d+)", completed.stdout)
    return int(match.group(1)) if match else 0


def _cjk_font_installed():
    fc_list = shutil.which("fc-list")
    if fc_list is None:
        return False
    completed = subprocess.run(
        [fc_list, ":family"],
        check=False,
        capture_output=True,
        text=True,
    )
    return "Noto Sans CJK TC" in completed.stdout


def _stage(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    wrapper = bindir / "xelatex-nonescape"
    shutil.copy(_ROOT / "container/xelatex-nonescape", wrapper)
    wrapper.chmod(0o755)
    (bindir / "xelatex").symlink_to(wrapper)
    share = tmp_path / "share"
    share.mkdir()
    for child in (_ROOT / "colophon/share").iterdir():
        dest = share / child.name
        if child.name == "lock-diagram.lua":
            text = child.read_text(encoding="utf-8").replace(
                "execpath: /usr/local/bin/xelatex-nonescape",
                f"execpath: {wrapper}",
            )
            dest.write_text(text, encoding="utf-8")
        else:
            dest.symlink_to(child)
    (share / "diagram.lua").symlink_to(_ROOT / "vendor/diagram/diagram.lua")
    return wrapper, share


def _bind(monkeypatch, tmp_path):
    wrapper, share = _stage(tmp_path)
    # The image stamps reference.docx at build time. Pandoc refuses a
    # missing file. A default reference is enough to compile the fence.
    templates = share / "templates"
    source = templates.resolve()
    templates.unlink()
    shutil.copytree(source, templates)
    for lane in ("InstruMeasure", "Weft", "Investor"):
        dest = templates / lane / "reference.docx"
        subprocess.run(
            [
                "pandoc",
                "-o",
                str(dest),
                "--print-default-data-file",
                "reference.docx",
            ],
            check=True,
        )
    monkeypatch.setattr("colophon.render_plan.SHARE_ROOT", str(share))
    monkeypatch.setattr("colophon.render_plan.XELATEX_BIN", str(wrapper))
    monkeypatch.setattr("colophon.templates.SHARE_ROOT", str(share))
    monkeypatch.setenv("TEXINPUTS", _TEXINPUTS + os.environ.get("TEXINPUTS", ""))
    monkeypatch.setenv(
        "PATH", f"{wrapper.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    )
    return wrapper


def _pdf_text(pdf, tmp_path, name):
    path = tmp_path / name
    path.write_bytes(pdf)
    completed = subprocess.run(
        ["pdftotext", "-raw", str(path), "-"],
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    return completed.stdout.decode("utf-8", "replace")


def test_xelatex_argv_rejects_absolute_and_parent_names():
    with pytest.raises(RenderPlanError):
        xelatex_argv("/tmp/job.tex")
    with pytest.raises(RenderPlanError):
        xelatex_argv("../job.tex")
    with pytest.raises(RenderPlanError):
        xelatex_argv("nested/../../job.tex")
    argv = xelatex_argv("job.tex")
    assert argv[-1] == "job.tex"
    assert "-output-directory" not in " ".join(argv)
    assert "-cnf-line=openin_any=p" in argv
    assert "-cnf-line=openout_any=p" in argv


def test_dockerfile_compiles_by_relative_name():
    text = (_ROOT / "container/Dockerfile.endleaf").read_text(encoding="utf-8")
    assert "xelatex -interaction=nonstopmode -halt-on-error cjk.tex;" in text
    assert "xelatex -interaction=nonstopmode -halt-on-error packages-once.tex;" in text
    assert (
        "xelatex -interaction=nonstopmode -halt-on-error floorplan-two-room.tex;"
        in text
    )
    assert "-output-directory=/tmp" not in text
    assert (
        "xelatex -interaction=nonstopmode -halt-on-error -output-directory" not in text
    )
    for line in text.splitlines():
        if "xelatex" in line:
            assert "/tmp/" not in line


def test_shipped_tex_inputs_are_kpathsea_names():
    paths = list((_ROOT / "colophon/share").rglob("*"))
    paths.append(_ROOT / "vendor/diagram/diagram.lua")
    paths.append(_ROOT / "colophon/share/lock-diagram.lua")
    seen = 0
    for path in paths:
        if path.suffix not in {".tex", ".sty", ".latex", ".lua"}:
            continue
        text = path.read_text(encoding="utf-8")
        for name in _ABS_INPUT.findall(text):
            seen += 1
            assert not name.startswith("/"), f"{path} inputs {name}"
            assert ".." not in name.split("/"), f"{path} inputs {name}"
    assert seen > 0


def test_fence_engine_uses_a_relative_tex_name():
    text = (_ROOT / "vendor/diagram/diagram.lua").read_text(encoding="utf-8")
    assert "'tikz-image.tex'" in text
    assert "-output-directory" not in text
    assert (
        "tikz_file"
        not in text.split("basename only", 1)[-1].split("return read_file", 1)[0]
    )


@pytest.mark.skipif(_XELATEX is None, reason="xelatex is not installed")
def test_wrapper_compiles_an_absolute_path_under_openin_p(tmp_path):
    wrapper, _share = _stage(tmp_path)
    (tmp_path / "job.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nHello.\n\\end{document}\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            str(wrapper),
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-cnf-line=openin_any=p",
            "-cnf-line=openout_any=p",
            "-output-directory",
            str(tmp_path),
            str(tmp_path / "job.tex"),
        ],
        cwd="/",
        check=False,
        timeout=60,
        capture_output=True,
    )
    log = (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")
    assert completed.returncode == 0, log[-1200:]
    assert (tmp_path / "job.pdf").is_file()
    assert "Not reading" not in log
    parent = f"{tmp_path}/../{tmp_path.name}/job.tex"
    refused = subprocess.run(
        [
            str(wrapper),
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-cnf-line=openin_any=p",
            parent,
        ],
        cwd="/",
        check=False,
        timeout=60,
        capture_output=True,
    )
    assert refused.returncode != 0
    assert b"Not reading" in refused.stdout or b"Not reading" in refused.stderr


@pytest.mark.skipif(
    _XELATEX is None
    or _PANDOC is None
    or _PDFTOTEXT is None
    or _INKSCAPE is None
    or _pandoc_major() < 3,
    reason="xelatex, pandoc 3, pdftotext, or inkscape is not installed",
)
@pytest.mark.skipif(
    not _cjk_font_installed(), reason="Noto Sans CJK TC is not installed"
)
def test_openin_jobs_compile(tmp_path, monkeypatch, capsysbinary):
    """The jobs the stale image rejected as invalid. openin_any=p stays on."""
    _bind(monkeypatch, tmp_path)
    jobs = (
        (
            "document-shell-pdf",
            "document-shell",
            "pdf",
            "Hello from the document shell.",
            0,
        ),
        (
            "document-shell-html",
            "document-shell",
            "html",
            "Hello from the document shell.",
            0,
        ),
        ("fence-pdf", "document-shell", "pdf", _FENCE, 0),
        ("fence-html", "document-shell", "html", _FENCE, 0),
        ("fence-docx", "document-shell", "docx", _FENCE, 0),
        ("tex-error", "circuits", "pdf", "\\thisisnotacommand", 10),
    )
    for name, template_id, fmt, body, expect in jobs:
        payload = json.dumps(
            {
                "lane": "Weft",
                "outputFormat": fmt,
                "templateId": template_id,
                "body": body,
            }
        ).encode("utf-8")
        code = render_to_stdout(payload)
        captured = capsysbinary.readouterr()
        err = captured.err.decode("utf-8", "replace")
        assert "ENDLEAF_STATUS invalid" not in err, name + "\n" + err[-2000:]
        assert code != 12, name
        assert code == expect, name + "\n" + err[-2000:]
        if expect != 0:
            assert "ENDLEAF_STATUS render_error" in err
            continue
        assert "ENDLEAF_STATUS ok" in err
        data = captured.out
        if fmt == "pdf":
            assert data.startswith(b"%PDF"), name
        elif fmt == "html":
            assert b"<html" in data.lower(), name
        else:
            assert data.startswith(b"PK"), name
        if "fence" not in name:
            continue
        if fmt == "html":
            # HTML embeds the fence as SVG. Inkscape outlines the glyphs, so
            # the characters are checked on the PDF jobs. A failed TikZ
            # compile never produces this SVG.
            text = data.decode("utf-8", "replace")
            blobs = re.findall(r"base64,([A-Za-z0-9+/=\s]+)", text)
            assert blobs, name
            svg = b"".join(base64.b64decode(re.sub(r"\s+", "", blob)) for blob in blobs)
            assert b"<svg" in svg, name
            assert len(svg) > 500, name
            continue
        if fmt == "docx":
            # Word gets the same outlined SVG, plus a PNG preview. The
            # characters are checked on the PDF of this fence.
            archive = zipfile.ZipFile(io.BytesIO(data))
            svgs = [
                archive.read(item)
                for item in archive.namelist()
                if item.endswith(".svg")
            ]
            assert svgs, name
            assert b"<svg" in svgs[0], name
            assert len(svgs[0]) > 500, name
            continue
        assert "幫浦" in _pdf_text(data, tmp_path, f"{name}.pdf"), name
