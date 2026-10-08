# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R57: second pass for citations, texWarnings counts, typed cause."""

import json
import shutil
import subprocess

import pytest

from colophon.diagnostics import first_tex_error, parse_stderr
from colophon.enums import parse_job
from colophon.job_result import job_record
from colophon.render_plan import build_render_plan, source_needs_aux_pass
from colophon.runner import Outcome
from colophon.tex_log import (
    CAUSE_CODES,
    count_tex_warnings,
    error_cause,
    parse_tex_warnings,
    tex_warn_line,
)
from colophon.worker import create_app
from tests.colophon.conftest import valid_body
from tests.colophon.test_fulldoc import _bind_tex, _render, _type_ready

_LOG = """\
This is XeTeX, Version 3.141592653-2.6-0.999994 (TeX Live 2022/Debian)
Overfull \\hbox (12.1pt too wide) in paragraph at lines 5--7
[]\\TU/TeXGyrePagella(0)/m/n/10 averyveryverylongunbreakabletoken
Overfull \\vbox (3.0pt too high) has occurred while \\output is active
Underfull \\hbox (badness 10000) in paragraph at lines 9--9
LaTeX Warning: Reference `tab:missing' on page 1 undefined on input line 12.
LaTeX Warning: Citation `nokey' on page 1 undefined on input line 14.
LaTeX Warning: Citation `otherkeythatisverylongandwrapsthelogline' on page 1 und
efined on input line 15.
LaTeX Warning: There were undefined references.
"""


def test_counts_each_key_from_the_final_log():
    assert count_tex_warnings(_LOG) == {
        "overfull": 2,
        "underfull": 1,
        "undefinedRef": 1,
        "undefinedCite": 2,
    }
    assert count_tex_warnings("") == dict.fromkeys(
        ("overfull", "underfull", "undefinedRef", "undefinedCite"), 0
    )


def test_warn_line_is_absent_when_clean_and_round_trips_otherwise():
    assert tex_warn_line(count_tex_warnings("clean log")) is None
    line = tex_warn_line(count_tex_warnings(_LOG))
    assert line == (
        'ENDLEAF_TEXWARN {"overfull":2,"underfull":1,"undefinedRef":1,"undefinedCite":2}'
    )
    stderr = b"ENDLEAF_STATUS ok\n" + line.encode() + b"\n"
    assert parse_tex_warnings(stderr) == {
        "overfull": 2,
        "underfull": 1,
        "undefinedRef": 1,
        "undefinedCite": 2,
    }
    assert parse_tex_warnings(b"ENDLEAF_STATUS ok\n") is None
    assert parse_tex_warnings(b"ENDLEAF_TEXWARN {not json}\n") is None
    assert parse_tex_warnings(b'ENDLEAF_TEXWARN {"overfull":-1}\n') is None
    assert parse_tex_warnings(b'ENDLEAF_TEXWARN {"overfull":"3"}\n') is None
    assert (
        parse_tex_warnings(
            b'ENDLEAF_TEXWARN {"overfull":0,"underfull":0,"undefinedRef":0,"undefinedCite":0}\n'
        )
        is None
    )
    # The existing meters dict is unchanged by the new line.
    meters, _diag = parse_stderr(
        b'ENDLEAF_METERS {"memoryPeak":1,"pidsPeak":2}\n' + stderr
    )
    assert meters == {"memoryPeak": 1, "pidsPeak": 2}


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("LaTeX Error: Can be used only in preamble.", "preambleOnly"),
        ("LaTeX Error: Environment tabularx undefined.", "undefinedEnvironment"),
        (
            "LaTeX Error: \\begin{itemize} on input line 4 ended by \\end{enumerate}.",
            "environmentMismatch",
        ),
        ("Undefined control sequence.", "undefinedCommand"),
        ("Missing $ inserted.", "mathMode"),
        ("Double subscript.", "mathMode"),
        ("Missing } inserted.", "braces"),
        ("Extra }, or forgotten \\endgroup.", "braces"),
        ("Too many }'s.", "braces"),
        ("Paragraph ended before \\textbf  was complete.", "unclosedArgument"),
        ("Runaway argument?", "unclosedArgument"),
        ("Extra alignment tab has been changed to \\cr.", "tableColumns"),
        ("Misplaced \\noalign.", "tableRule"),
        ("LaTeX Error: There's no line here to end.", "lineBreak"),
        ("LaTeX Error: File `natbib.sty' not found.", "fileNotFound"),
    ],
)
def test_cause_table_maps_the_first_error(message, code):
    assert error_cause(message) == code
    assert code in CAUSE_CODES


def test_cause_table_is_bounded_and_leaves_unknown_errors_untyped():
    assert len(CAUSE_CODES) == 11
    assert len(set(CAUSE_CODES)) == 11
    assert (
        error_cause("Package sysml-tikz Error: layout_overlap: keyword at 1,2") is None
    )
    assert error_cause("fulldoc exceeds maxPages 16 (got 17 pages)") is None
    assert error_cause("") is None
    assert error_cause(None) is None


def test_first_tex_error_carries_the_cause_only_when_typed():
    found = first_tex_error("./job.tex:9: Undefined control sequence.\n")
    assert found["cause"] == "undefinedCommand"
    overlap = first_tex_error(
        "./job.tex:90: Package sysml-tikz Error: layout_overlap: x\n"
    )
    assert "cause" not in overlap
    _meters, diag = parse_stderr(
        b'ENDLEAF_DIAG {"engine":"tex","message":"Extra alignment tab has been changed to \\\\cr.","file":"job.tex","line":3,"fence":null}\n'
    )
    assert diag["cause"] == "tableColumns"


def _tex_job(source):
    return parse_job(
        valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=source)
    )


@pytest.mark.parametrize(
    "body",
    [
        "As shown~\\cite{k}.",
        "See (\\eqref{eq:a}).",
        "\\tableofcontents",
        "Two~\\cite{a,b}.",
    ],
)
def test_citation_eqref_and_toc_take_the_second_pass(body):
    assert source_needs_aux_pass(body)
    plan = build_render_plan(_tex_job(body))
    assert len(plan.commands) == 2
    assert plan.commands[0] == plan.commands[1]


@pytest.mark.parametrize(
    "body", ["\\citep{k}", "\\nocite{k}", "\\citetext", "Plain text.", "\\citation"]
)
def test_other_bodies_stay_one_pass(body):
    assert not source_needs_aux_pass(body)
    assert len(build_render_plan(_tex_job(body)).commands) == 1


def test_job_record_carries_tex_warnings_only_when_counted():
    counts = {"overfull": 3, "underfull": 0, "undefinedRef": 1, "undefinedCite": 0}
    assert job_record("ok", 0.5, 1, 2, tex_warnings=counts)["texWarnings"] == counts
    assert "texWarnings" not in job_record("ok", 0.5, 1, 2)
    zero = dict.fromkeys(counts, 0)
    assert "texWarnings" not in job_record("ok", 0.5, 1, 2, tex_warnings=zero)


def test_success_header_exposes_tex_warnings(config, switch_path, monitor, auth):
    from colophon.killswitch import KillSwitch
    from colophon.runner import Supervisor

    counts = {"overfull": 2, "underfull": 5, "undefinedRef": 0, "undefinedCite": 1}
    outcome = Outcome(
        kind="ok",
        body=b"%PDF-1.4",
        content_type="application/pdf",
        wall_sec=0.5,
        memory_peak=100,
        pids_peak=3,
        tex_warnings=counts,
    )

    class _Runner:
        def __call__(self, job, name, abort_event):
            return outcome

    app = create_app(
        config, KillSwitch(switch_path), monitor, Supervisor(_Runner(), 10)
    )
    response = app.test_client().post("/v1/jobs", json=valid_body(), headers=auth)
    record = json.loads(response.headers["X-Endleaf-Job"])
    assert record["texWarnings"] == counts
    assert response.headers["X-Colophon-Job"] == response.headers["X-Endleaf-Job"]


_LOCAL = pytest.mark.skipif(
    shutil.which("xelatex") is None
    or shutil.which("pdftotext") is None
    or not _type_ready(),
    reason="xelatex, pdftotext, or TeX Gyre Pagella is not installed",
)

_CITE_ONLY = """\
\\section{Method}
The rig follows Harris~\\cite{harris2006} and the drive standard~\\cite{iec60034}.
\\begin{thebibliography}{9}
\\bibitem{harris2006} T. A. Harris, \\emph{Rolling Bearing Analysis}, 2006.
\\bibitem{iec60034} IEC 60034-1, Rotating electrical machines \\& ratings, 2022.
\\end{thebibliography}
"""


def _pdf_text(tmp_path, pdf):
    path = tmp_path / "out.pdf"
    path.write_bytes(pdf)
    done = subprocess.run(
        ["pdftotext", "-raw", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout


@_LOCAL
def test_cite_only_fulldoc_resolves_and_is_clean(tmp_path, monkeypatch):
    """Live 2026-10-08: this body (no \\ref) rendered [?] [?] on one pass."""
    _bind_tex(monkeypatch, tmp_path)
    code, pdf, err = _render(
        valid_body(
            templateId="fulldoc", outputFormat="pdf", lane="Weft", body=_CITE_ONLY
        ),
        monkeypatch,
    )
    assert code == 0, err[-2000:]
    text = _pdf_text(tmp_path, pdf)
    assert "[1]" in text and "[2]" in text, text
    assert "[?]" not in text, text
    assert "ENDLEAF_TEXWARN" not in err, err[-2000:]


@_LOCAL
def test_missing_key_and_wide_line_are_counted(tmp_path, monkeypatch):
    _bind_tex(monkeypatch, tmp_path)
    body = (
        "See \\ref{tab:none} and~\\cite{nokey}.\n\n"
        "\\noindent\\texttt{" + "x" * 120 + "}\n"
    )
    code, _pdf, err = _render(
        valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=body),
        monkeypatch,
    )
    assert code == 0, err[-2000:]
    counts = parse_tex_warnings(err.encode())
    assert counts is not None, err[-2000:]
    assert counts["undefinedRef"] == 1
    assert counts["undefinedCite"] == 1
    assert counts["overfull"] >= 1


@_LOCAL
@pytest.mark.parametrize(
    ("body", "cause"),
    [
        ("Hello \\nosuchmacro.", "undefinedCommand"),
        ("Index x_1 in text.", "mathMode"),
        ("\\begin{tabular}{ll}\na & b & c \\\\\n\\end{tabular}", "tableColumns"),
        (
            "\\begin{tabularx}{\\linewidth}{X}\na\\\\\n\\end{tabularx}",
            "undefinedEnvironment",
        ),
    ],
)
def test_render_error_carries_a_typed_cause(tmp_path, monkeypatch, body, cause):
    _bind_tex(monkeypatch, tmp_path)
    code, _pdf, err = _render(
        valid_body(templateId="fulldoc", outputFormat="pdf", lane="Weft", body=body),
        monkeypatch,
    )
    assert code == 10, err[-2000:]
    diag = json.loads(err.split("ENDLEAF_DIAG ", 1)[1].splitlines()[0])
    assert diag["cause"] == cause, diag
