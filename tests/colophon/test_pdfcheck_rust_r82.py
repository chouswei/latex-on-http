# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R82-IFACE. sandbox_render and the endleaf-pdfcheck binary.

The contract cases use a stand-in executable (a short Python script), so they need neither
cargo nor the oracle libraries. The cases marked "built binary" run the real binary and
skip when it is not built (see pdfcheck_support).
"""

import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from colophon import pdf_layout_check as reference
from colophon import sandbox_render as sr
from colophon.pdf_layout_check import parse_pdf_layout, pdf_layout_line
from tests.colophon.pdfcheck_support import (
    REAL,
    binary_or_skip,
    item_diffs,
    log_from_sidecar,
    real_samples,
    run_sidecar,
)

_ITEMS = [
    {
        "code": "pdf_margin_escape",
        "packages": ["pdf"],
        "message": "pg1: text runs 24.7 mm past the text block: 'this line runs far past the r…'",
        "page": 1,
        "box": [400.0, 484.1, 610.1, 494.1],
        "regionCount": 1,
        "overMm": 24.7,
    }
]
_LOG = ["pdfcheck guard page=1 otsuEm=0.010 usedEm=0.1", "pdfcheck noblock pages=1"]
_BLOCK_LOG = "ENDLEAF_PAGEBLOCK 1 72.27pt 72.27pt 468.0pt 648.0pt\n"

_FAKE = """#!{python}
import json, os, sys, time
mode = os.environ["FAKE_PDFCHECK_MODE"]
sys.stderr.write("FAKE-STDERR-NOISE ENDLEAF_PDFLAYOUT []\\n")
if mode == "version":
    print("endleaf-pdfcheck 0.1.0"); sys.exit(0)
if mode == "badversion":
    print("something else 1.0"); sys.exit(0)
seen = os.environ.get("FAKE_PDFCHECK_SEEN")
if seen:
    side = sys.argv[2] if len(sys.argv) > 2 else None
    pdf = sys.argv[3] if len(sys.argv) > 3 else None
    json.dump({{"argv": sys.argv[1:], "sidecar": json.load(open(side)) if side else None,
               "pdf": open(pdf, "rb").read().decode("latin-1") if pdf else None}}, open(seen, "w"))
if mode == "ok":
    sys.stdout.write(open(os.environ["FAKE_PDFCHECK_OUT"]).read()); sys.exit(0)
if mode == "exit":
    sys.stdout.write(open(os.environ["FAKE_PDFCHECK_OUT"]).read()); sys.exit(3)
if mode == "sleep":
    time.sleep(30); sys.exit(0)
"""


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A stand-in binary at PDFCHECK_BIN; job files go to tmp_path instead of /tmp."""
    exe = tmp_path / "endleaf-pdfcheck"
    exe.write_text(_FAKE.format(python=sys.executable), encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setattr(sr, "PDFCHECK_BIN", str(exe))
    monkeypatch.setattr(sr, "PDFCHECK_PDF", str(tmp_path / "job-pdfcheck.pdf"))
    monkeypatch.setattr(sr, "PDFCHECK_SIDECAR", str(tmp_path / "job-pdfcheck.json"))
    seen = tmp_path / "seen.json"
    monkeypatch.setenv("FAKE_PDFCHECK_SEEN", str(seen))

    def use(mode, stdout=None):
        monkeypatch.setenv("FAKE_PDFCHECK_MODE", mode)
        if stdout is not None:
            out = tmp_path / "out.txt"
            out.write_text(stdout, encoding="utf-8")
            monkeypatch.setenv("FAKE_PDFCHECK_OUT", str(out))
        return seen

    return use


def _job(template="fulldoc"):
    return SimpleNamespace(template_id=template)


def test_timeout_is_the_document_budget_plus_three_seconds_and_the_paths_are_the_contract():
    assert sr.PDFCHECK_TIMEOUT_SEC == reference.DOCUMENT_BUDGET_SEC + 3.0 == 5.0
    assert sr.PDFCHECK_BIN == "/usr/local/bin/endleaf-pdfcheck"
    assert (sr.PDFCHECK_PDF, sr.PDFCHECK_SIDECAR) == (
        "/tmp/job-pdfcheck.pdf",
        "/tmp/job-pdfcheck.json",
    )


def test_sandbox_render_no_longer_runs_the_python_checker():
    source = Path(sr.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\bcheck_pdf\b|\b_preload\b", source)


def test_sidecar_is_written_and_the_lines_come_from_the_binary_output(fake, capsys):
    seen = fake("ok", json.dumps({"items": _ITEMS, "log": _LOG}))
    sr._pdf_layout_check(_job(), b"%PDF-1.4 fake bytes", _BLOCK_LOG, None, 0)
    err = capsys.readouterr().err
    assert err == (
        "ENDLEAF_PDFLOG pdfcheck guard page=1 otsuEm=0.010 usedEm=0.1\n"
        "ENDLEAF_PDFLOG pdfcheck noblock pages=1\n" + pdf_layout_line(_ITEMS) + "\n"
    )
    assert parse_pdf_layout(err) == _ITEMS
    assert "FAKE-STDERR-NOISE" not in err  # the binary's stderr is dropped
    call = json.loads(seen.read_text())
    assert call["argv"] == ["--sidecar", sr.PDFCHECK_SIDECAR, sr.PDFCHECK_PDF]
    assert call["pdf"] == "%PDF-1.4 fake bytes"
    assert call["sidecar"] == {
        "templateId": "fulldoc",
        "blocks": {"1": [72.27, 72.27, 468.0, 648.0]},
        "marks": [],
        "shellPages": {},
        "texPages": [],
    }


def test_sidecar_types_and_marks_only_for_fulldoc(fake, capsys):
    seen = fake("ok", json.dumps({"items": [], "log": []}))
    log = (
        _BLOCK_LOG
        + "ENDLEAF_PAGEBLOCK 2 56.9055pt 56.9055pt 728.0pt 478.0pt\n"
        + "ENDLEAF_MARK p1 s 1 36700160 portrait\nENDLEAF_SHELLPAGE 3 2 landscape\n"
        + "Overfull \\hbox (30.0pt too wide) in paragraph at lines 3--4\n []\n\n[1]\n"
    )
    sr._pdf_layout_check(_job("document-shell"), b"%PDF", log, 1, 10)
    assert capsys.readouterr().err == ""  # no findings, no log lines: nothing to send
    side = json.loads(seen.read_text())["sidecar"]
    assert side == {
        "templateId": "document-shell",
        "blocks": {
            "1": [72.27, 72.27, 468.0, 648.0],
            "2": [56.9055, 56.9055, 728.0, 478.0],
        },
        "shellPages": {"3": 2},
        "texPages": [1],
    }
    sr._pdf_layout_check(_job("fulldoc"), b"%PDF", log, 1, 10)
    assert json.loads(seen.read_text())["sidecar"]["marks"] == [
        ["p1", "s", 1, 560.0, "p"]
    ]


@pytest.mark.parametrize("name", real_samples())
def test_sidecar_equals_the_real_sample_sidecar(name):
    """The sidecar sandbox_render builds equals the one the real-sample run recorded."""
    expected = json.loads((REAL / name / "sidecar.json").read_text(encoding="utf-8"))
    built = sr._pdfcheck_sidecar(
        _job(expected["templateId"]), log_from_sidecar(expected), 1, 10
    )
    assert built == expected
    assert list(built) == [
        k
        for k in ("templateId", "blocks", "marks", "shellPages", "texPages")
        if k in expected
    ]


@pytest.mark.parametrize(
    "mode, stdout",
    [
        (
            "exit",
            json.dumps({"items": _ITEMS, "log": _LOG}),
        ),  # a non-zero exit, even with good output
        ("ok", "not json"),
        ("ok", json.dumps([_ITEMS])),
        ("ok", json.dumps({"items": _ITEMS})),
        ("ok", json.dumps({"log": []})),
        ("ok", json.dumps({"items": ["x"], "log": []})),
        ("ok", json.dumps({"items": [], "log": [1]})),
        ("ok", json.dumps({"items": [], "log": []}) * 2),
        ("ok", ""),
    ],
)
def test_bad_exit_or_output_is_one_error_line(fake, capsys, mode, stdout):
    fake(mode, stdout)
    sr._pdf_layout_check(_job(), b"%PDF", _BLOCK_LOG, None, 0)
    assert capsys.readouterr().err == "ENDLEAF_PDFLOG pdfcheck error\n"


def test_timeout_kills_the_binary_and_gives_the_error_line(fake, capsys, monkeypatch):
    fake("sleep")
    monkeypatch.setattr(sr, "PDFCHECK_TIMEOUT_SEC", 0.5)
    start = time.monotonic()
    sr._pdf_layout_check(_job(), b"%PDF", _BLOCK_LOG, None, 0)
    assert time.monotonic() - start < 10
    assert capsys.readouterr().err == "ENDLEAF_PDFLOG pdfcheck error\n"


def test_missing_binary_is_an_error_line_in_a_job_and_an_image_error_at_start(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sr, "PDFCHECK_BIN", str(tmp_path / "absent"))
    monkeypatch.setattr(sr, "PDFCHECK_PDF", str(tmp_path / "job-pdfcheck.pdf"))
    monkeypatch.setattr(sr, "PDFCHECK_SIDECAR", str(tmp_path / "job-pdfcheck.json"))
    sr._pdf_layout_check(_job(), b"%PDF", _BLOCK_LOG, None, 0)
    assert capsys.readouterr().err == "ENDLEAF_PDFLOG pdfcheck error\n"
    with pytest.raises(OSError):
        sr.check_pdfcheck_binary()
    order = []
    monkeypatch.setattr(sr, "render_to_stdout", lambda raw: order.append("render") or 0)
    with pytest.raises(OSError):
        sr.main()
    assert order == []  # the sandbox fails before it reads or renders a job


def test_version_check_at_start(fake, monkeypatch):
    fake("version")
    sr.check_pdfcheck_binary()
    fake("badversion")
    with pytest.raises(RuntimeError):
        sr.check_pdfcheck_binary()
    fake("version")
    order = []
    monkeypatch.setattr(sr, "render_to_stdout", lambda raw: order.append("render") or 0)
    monkeypatch.setattr(
        sys, "stdin", SimpleNamespace(buffer=__import__("io").BytesIO(b"{}"))
    )
    with pytest.raises(SystemExit):
        sr.main()
    assert order == ["render"]


def test_render_deletes_both_pdfcheck_files_in_its_finally_block(tmp_path, monkeypatch):
    pdf_path, side_path = tmp_path / "job-pdfcheck.pdf", tmp_path / "job-pdfcheck.json"
    monkeypatch.setattr(sr, "PDFCHECK_PDF", str(pdf_path))
    monkeypatch.setattr(sr, "PDFCHECK_SIDECAR", str(side_path))
    attempted = []

    class _Path(type(Path())):
        """Keeps the test away from the host's /tmp: no glob there, unlink only under tmp_path."""

        def glob(self, pattern):
            return iter(()) if str(self) == "/tmp" else super().glob(pattern)

        def unlink(self, missing_ok=False):
            attempted.append(str(self))
            if str(self).startswith(str(tmp_path)):
                super().unlink(missing_ok=missing_ok)

    out = tmp_path / "out.pdf"
    out.write_bytes(b"%PDF-1.4")
    job = SimpleNamespace(
        template_id="document-shell",
        input_kind="markdown",
        output_format="pdf",
        source="x",
    )
    plan = SimpleNamespace(files={}, commands=[], output_path=str(out))
    monkeypatch.setattr(sr, "Path", _Path)
    monkeypatch.setattr(sr, "parse_job", lambda payload: job)
    monkeypatch.setattr(sr, "build_render_plan", lambda j: plan)

    def check(job, data, log, body_start, body_lines):
        pdf_path.write_bytes(data)
        side_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sr, "_pdf_layout_check", check)
    monkeypatch.setattr(
        sys, "stdout", SimpleNamespace(buffer=__import__("io").BytesIO())
    )
    assert sr.render_to_stdout(b"{}") == 0
    assert str(pdf_path) in attempted and str(side_path) in attempted
    assert not pdf_path.exists() and not side_path.exists()


# -- built binary ---------------------------------------------------------------------------------


def test_built_binary_answers_version_and_the_start_check_passes(monkeypatch):
    binary = binary_or_skip()
    monkeypatch.setattr(sr, "PDFCHECK_BIN", binary)
    sr.check_pdfcheck_binary()


def test_built_binary_through_sandbox_render_margin_escape_and_tex_named_page(
    tmp_path, monkeypatch, capsys
):
    from tests.colophon.test_pdf_layout_check_r81 import pdf, text

    monkeypatch.setattr(sr, "PDFCHECK_BIN", binary_or_skip())
    monkeypatch.setattr(sr, "PDFCHECK_PDF", str(tmp_path / "job-pdfcheck.pdf"))
    monkeypatch.setattr(sr, "PDFCHECK_SIDECAR", str(tmp_path / "job-pdfcheck.json"))
    faulty = pdf(
        [text(400, 680, "this line runs far past the right edge of the block")]
    )
    sr._pdf_layout_check(_job(), faulty, _BLOCK_LOG, None, 0)
    items = parse_pdf_layout(capsys.readouterr().err)
    assert [i["code"] for i in items] == ["pdf_margin_escape"]
    # OD-PDF-4: TeX names page 1 with an overfull row, so the margin escape is dropped.
    named = (
        _BLOCK_LOG
        + "Overfull \\hbox (30.0pt too wide) in paragraph at lines 3--4\n []\n\n[1]\n"
    )
    sr._pdf_layout_check(_job(), faulty, named, 1, 10)
    assert parse_pdf_layout(capsys.readouterr().err) == []
    # Garbage in is a skip note from the binary, not an error line.
    sr._pdf_layout_check(_job(), b"not a pdf", _BLOCK_LOG, None, 0)
    err = capsys.readouterr().err
    assert "pdfcheck error" not in err
    assert [i["code"] for i in parse_pdf_layout(err)] == ["pdf_check_skipped"]


@pytest.mark.parametrize("name", real_samples())
def test_built_binary_gives_the_python_findings_on_the_real_samples(
    name, tmp_path, monkeypatch, capsys
):
    """Real Endleaf output: the binary's findings equal the recorded Python findings.

    Default budgets through sandbox_render (as in the image), lifted budgets directly.
    """
    binary = binary_or_skip()
    folder = REAL / name
    sidecar = json.loads((folder / "sidecar.json").read_text(encoding="utf-8"))
    data = (folder / "out.pdf").read_bytes()
    lifted = json.loads((folder / "python-lifted.json").read_text(encoding="utf-8"))
    default = json.loads((folder / "python-default.json").read_text(encoding="utf-8"))
    got = run_sidecar(binary, sidecar, folder / "out.pdf", tmp_path)
    assert (
        item_diffs(lifted["items"], got["items"]) == [] and got["log"] == lifted["log"]
    )
    monkeypatch.setattr(sr, "PDFCHECK_BIN", binary)
    monkeypatch.setattr(sr, "PDFCHECK_PDF", str(tmp_path / "job-pdfcheck.pdf"))
    monkeypatch.setattr(sr, "PDFCHECK_SIDECAR", str(tmp_path / "job-pdfcheck.json"))
    sr._pdf_layout_check(
        _job(sidecar["templateId"]), data, log_from_sidecar(sidecar), 1, 10
    )
    err = capsys.readouterr().err
    assert "pdfcheck error" not in err
    assert [
        line[len("ENDLEAF_PDFLOG ") :]
        for line in err.splitlines()
        if line.startswith("ENDLEAF_PDFLOG ")
    ] == default["log"]
    assert item_diffs(default["items"], parse_pdf_layout(err)) == []
