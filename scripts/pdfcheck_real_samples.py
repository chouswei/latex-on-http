#!/usr/bin/env python3
"""Regenerate tests/fixtures/pdfcheck-real/** from real worker output (ENDLEAF-R82 probe).

Each sample is a job payload rendered by the box's local render image through the
worker's own ``colophon.sandbox_render`` (a driver script, ``pdfcheck_real_driver.py``,
runs inside the image). The driver captures the final TeX log where the worker calls the
PDF layout check, builds the R82-IFACE sidecar with the image's own functions, and runs the
in-image Python checker twice: budgets lifted and default budgets.

Podman command (one per sample; no network, read-only root, the worker's limits; the
driver directory is mounted read-only and the result is one JSON object on stdout):

  podman run --rm --network=none --read-only \\
    --tmpfs /tmp:rw,nosuid,nodev,size=512m,mode=1777 --user 10001 --cpus=1 \\
    --memory=2048m --pids-limit=256 --cap-drop=ALL --security-opt=no-new-privileges \\
    --workdir=/tmp --env HOME=/tmp --env TMPDIR=/tmp --env XDG_CACHE_HOME=/tmp/cache \\
    --env XDG_CONFIG_HOME=/tmp/config --env TEXMFVAR=/tmp/texmf-var \\
    --env TEXMFHOME=/tmp/texmf-home --env LANG=C.UTF-8 -v <drvdir>:/drv:ro \\
    --entrypoint python3 localhost/endleaf-render:libs /drv/pdfcheck_real_driver.py /drv/p.json

Usage: scripts/pdfcheck_real_samples.py [--image TAG] [--only NAME ...]
Never pulls or pushes an image; never calls a live worker.
"""
import argparse
import base64
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests/fixtures/pdfcheck-real"
KINDS = ROOT / "tests/colophon/fixtures/kinds"
OWNED = ROOT / "colophon/share/templates/owned"
LANE = "Investor"


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def _tex(template, body, **extra):
    return dict(templateId=template, lane=LANE, outputFormat="pdf", body=body, **extra)


def _md(body, **extra):
    return _tex("document-shell", body, **extra)


def _shell_doc(title, prose, caption):
    return (
        f"# {title}\n\n{prose}\n\n"
        '```{.tikz caption="' + caption + '"}\n'
        "\\begin{tikzpicture}\n"
        "\\draw (0,0) rectangle (4,1.5);\n"
        "\\node at (2,0.75) {" + title + "};\n"
        "\\end{tikzpicture}\n```\n\n"
        "```\nprint('" + title + "')\n```\n"
    )


_LONG_URL = "https://example.org/" + "very-long-path-segment-without-any-break-" * 6 + "end"

_FULLDOC_MARKS = (
    "\\title{Two parts}\\author{InkMirage}\\maketitle\n"
    "\\section{\\EndleafMark{s1}{s}First}\\label{sec:one}\n"
    "\\EndleafMark{p1}{s}The first part. " + "Lorem ipsum dolor sit amet. " * 40 + "\\EndleafMark{p1}{e}\n\n"
    "\\begin{figure}[ht]\\centering\\EndleafMark{fig:a}{r}\n"
    "\\begin{tikzpicture}\\draw (0,0) rectangle (4,1.5);\\node at (2,0.75){box};\\end{tikzpicture}\n"
    "\\caption{A box.\\label{fig:a}}\\end{figure}\n\n"
    "\\section{Second}\n"
    "\\EndleafMark{p2}{s}The second part. " + "Consectetur adipiscing elit. " * 60 + "\\EndleafMark{p2}{e}\n"
)

_FULLDOC_OVERHANG = _FULLDOC_MARKS.replace(
    "\\begin{tikzpicture}\\draw (0,0) rectangle (4,1.5);",
    "\\begin{tikzpicture}\\draw (0,0) rectangle (17,1.5);",
) + (
    "\n\\newpage\\EndleafMark{p4}{s}Figure with a label on its line.\\par\\medskip\n"
    "\\begin{tikzpicture}\\draw[line width=2pt] (0,0) -- (6,0);\\node at (3,0) {LABEL ON LINE};\\end{tikzpicture}\\EndleafMark{p4}{e}\n"
    "\n\\EndleafMark{p3}{s}Link \\texttt{" + _LONG_URL + "} ends here.\\EndleafMark{p3}{e}\n"
)

SAMPLES = [
    ("sysml-interconnection", "sysml", lambda: _tex("sysml", _read(KINDS / "sysml.tex"))),
    (
        "shell-label-on-stroke",
        "document-shell",
        lambda: _md(
            "# Label on a stroke\n\nThe node text sits on top of the drawn line.\n\n"
            '```{.tikz caption="Label on a line"}\n\\begin{tikzpicture}\n\\draw[line width=2pt] (0,0) -- (6,0);\n'
            "\\node at (3,0) {LABEL ON LINE};\n\\end{tikzpicture}\n```\n"
        ),
    ),
    (
        "shell-tikz-and-code",
        "document-shell",
        lambda: _md(
            "# Pump test report\n\nProse and $E=mc^2$.\n\n"
            '```{.tikz caption="Figure 1. Pump loop"}\n\\begin{circuitikz}\n  \\draw (0,0) to[R, l=$R_1$] (3,0);\n\\end{circuitikz}\n```\n\n'
            "```\nfor i in range(3):\n    print(i)\n```\n\nMore text after the code.\n"
        ),
    ),
    (
        "shell-long-code-line",
        "document-shell",
        lambda: _md(
            "# Long line\n\nA fence with a very long line:\n\n```\n"
            + "x = '" + "0123456789" * 22 + "'\n```\n\nSee " + _LONG_URL + " for more.\n"
        ),
    ),
    ("fulldoc-two-parts", "fulldoc", lambda: _tex("fulldoc", _FULLDOC_MARKS)),
    ("fulldoc-overhang", "fulldoc", lambda: _tex("fulldoc", _FULLDOC_OVERHANG)),
    (
        "stocklabel",
        "stocklabel",
        lambda: dict(
            _tex("stocklabel", _read(OWNED / "stocklabel/example.tex")),
            labelSize={"widthMm": 89.8, "heightMm": 29.0, "marginXMm": 2.95, "marginYMm": 1.55},
        ),
    ),
    ("circuits", "circuits", lambda: _tex("circuits", _read(KINDS / "circuits.tex"))),
    ("plots", "plots", lambda: _tex("plots", _read(OWNED / "plots/example.tex"))),
    (
        "pidcircuit",
        "pidcircuit",
        lambda: _tex(
            "pidcircuit",
            "\\begin{tikzpicture}[circuit pid ISO14617]\n  \\node[valve={}] (v) at (0,0) {};\n"
            "  \\node[valve={}] (w) at (3,0) {};\n  \\draw (v) -- (w);\n\\end{tikzpicture}\n",
        ),
    ),
    (
        "shell-zh-tw",
        "document-shell",
        lambda: _md(_shell_doc("幫浦測試報告", "這是一份繁體中文文件，內含公式與圖。液位維持在範圍內。", "圖一　幫浦迴路")),
    ),
    (
        "shell-zh-cn",
        "document-shell",
        lambda: _md(_shell_doc("水泵测试报告", "这是一份简体中文文档，包含公式与图。液位保持在范围内。", "图一　水泵回路")),
    ),
    (
        "shell-ko",
        "document-shell",
        lambda: _md(_shell_doc("펌프 시험 보고서", "이 문서는 한국어로 작성되었습니다. 수위는 허용 범위 안에 있습니다.", "그림 1. 펌프 회로")),
    ),
    (
        "shell-ja",
        "document-shell",
        lambda: _md(_shell_doc("ポンプ試験報告書", "この文書は日本語で書かれています。水位は範囲内に保たれています。", "図1　ポンプ回路")),
    ),
    (
        "shell-landscape",
        "document-shell",
        lambda: _md(
            "# Landscape page\n\nA wide figure on a landscape A4 page.\n\n"
            '```{.tikz caption="A wide box"}\n\\begin{tikzpicture}\n\\draw (0,0) rectangle (20,6);\n\\node at (10,3) {wide};\n\\end{tikzpicture}\n```\n',
            orientation="landscape",
        ),
    ),
]


def _podman(image, drvdir):
    return [
        "podman", "run", "--rm", "--network=none", "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m,mode=1777", "--user", "10001", "--cpus=1",
        "--memory=2048m", "--pids-limit=256", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--workdir=/tmp", "--env", "HOME=/tmp", "--env", "TMPDIR=/tmp",
        "--env", "XDG_CACHE_HOME=/tmp/cache", "--env", "XDG_CONFIG_HOME=/tmp/config",
        "--env", "TEXMFVAR=/tmp/texmf-var", "--env", "TEXMFHOME=/tmp/texmf-home",
        "--env", "LANG=C.UTF-8", "-v", f"{drvdir}:/drv:ro",
        "--entrypoint", "python3", image, "/drv/pdfcheck_real_driver.py", "/drv/p.json",
    ]


def _dump(path, obj):
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _image_info(image):
    fmt = "{{.Id}}|{{range .Config.Env}}{{println .}}{{end}}"
    text = subprocess.run(["podman", "image", "inspect", image, "--format", fmt],
                          capture_output=True, text=True, check=True).stdout
    ident, *envs = text.splitlines()
    commit = next((e.split("=", 1)[1] for e in envs if e.startswith("ENDLEAF_GIT_COMMIT=")), "?")
    return ident[:12], commit


def _summary(result):
    codes = [item.get("code") or item.get("kind") for item in result["items"]]
    skips = [c for c in codes if c and "skipped" in str(c)]
    return len(result["items"]), skips


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default="localhost/endleaf-render:libs")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    image_id, commit = _image_info(args.image)
    rows = []
    for name, kind, make in SAMPLES:
        if args.only and name not in args.only:
            continue
        payload = make()
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o755)
            shutil.copy(ROOT / "scripts/pdfcheck_real_driver.py", tmp)
            Path(tmp, "p.json").write_text(json.dumps(payload), encoding="utf-8")
            for f in Path(tmp).iterdir():
                os.chmod(f, 0o644)
            done = subprocess.run(_podman(args.image, tmp), capture_output=True, timeout=300)
        try:
            res = json.loads(done.stdout)
        except ValueError:
            print(f"{name}: no result\n{done.stderr.decode('utf-8', 'replace')[-800:]}", file=sys.stderr)
            continue
        if res.get("exit") != 0 or "sidecar" not in res:
            print(f"{name}: render exit {res.get('exit')} {done.stderr.decode('utf-8','replace')[-600:]}", file=sys.stderr)
            continue
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        _dump(d / "payload.json", payload)
        pdf = base64.b64decode(res["pdfBase64"])
        (d / "out.pdf").write_bytes(pdf)
        _dump(d / "sidecar.json", res["sidecar"])
        _dump(d / "python-lifted.json", res["lifted"])
        _dump(d / "python-default.json", res["default"])
        nl, sl = _summary(res["lifted"])
        nd, sd = _summary(res["default"])
        rows.append((name, kind, res.get("pages"), nl, nd, len(pdf), sl + sd))
        print(name, kind, res.get("pages"), nl, nd, len(pdf), flush=True)
    if args.only:
        return
    lines = [
        "# pdfcheck-real: real worker output for the Rust PDF layout checker (ENDLEAF-R82 probe)",
        "",
        f"- image: {args.image}, id {image_id}, ENDLEAF_GIT_COMMIT {commit}",
        f"- generated: {datetime.date.today().isoformat()} by scripts/pdfcheck_real_samples.py",
        "- python-lifted.json: colophon.pdf_layout_check.check_pdf in the image with budgets lifted;",
        "  python-default.json: default budgets (0.25 s per page, 2.0 s per document). Both are `{items, log}`.",
        "- sidecar.json: R82-IFACE shape, built in the image with page_blocks, page_marks (fulldoc only),",
        "  shell_pages and texPages = overfull-row pages | layout-warning pages.",
        "",
        "| sample | kind | pages | findings lifted | findings default | pdf bytes | skips |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, kind, pages, nl, nd, size, skips in rows:
        lines.append(f"| {name} | {kind} | {pages} | {nl} | {nd} | {size} | {', '.join(skips) or '-'} |")
    (OUT / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
