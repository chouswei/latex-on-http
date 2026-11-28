# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ENDLEAF-R82-PARITY. The Rust binary against the Python reference oracle.

Every corpus PDF and every real sample goes through both endleaf-pdfcheck (``--sidecar``)
and colophon.pdf_layout_check.check_pdf, budgets lifted, with the same template, blocks,
marks, shell pages and TeX pages. Items must agree on code, packages, message, page,
regionCount, overMm, partId, fenceNumber and count, each box edge within 0.5 pt, and the
log lines must be equal. Groups:

- corpus: the 21 repository PDFs (rust/endleaf-pdfcheck/corpus.txt), findings and the
  per-page line dump (text and box, order-free);
- synth: the constructed cases of test_pdf_layout_check_r81.py;
- gap: the crate's gap fixtures (rust/endleaf-pdfcheck/tests/fixtures/gap), with the line
  dump where the manifest says ``both``;
- real: tests/fixtures/pdfcheck-real (worker output, sidecars as sandbox_render writes them),
  findings and line dump.

The only exceptions are the cases in ``ACCEPTED``: deliberate differences, each a line of
rust/endleaf-pdfcheck/PARITY.md, where the binary's exact output is pinned instead. Real
worker output (XeLaTeX through xdvipdfmx) never takes those paths.

Runs only with the pinned oracle libraries (tests/requirements-pdfcheck-oracle.txt) and a
built binary; it skips otherwise, and fails instead with ENDLEAF_PDFCHECK_REQUIRED=1 (the
pdfcheck-parity CI job).
"""

import json
import subprocess
from pathlib import Path

import pytest

from tests.colophon.pdfcheck_support import (
    CORPUS_LIST,
    CRATE,
    GAP,
    LIFTED,
    REAL,
    ROOT,
    binary_or_skip,
    item_diffs,
    oracle_kwargs,
    oracle_or_skip,
    real_samples,
    run_sidecar,
)

_ENCRYPTED_NOTE = {
    "items": [
        {
            "code": "pdf_check_skipped",
            "packages": ["pdf"],
            "message": "pdf layout check stopped (encrypted) before pg1",
        }
    ],
    "log": [],
}
_LZW_EARLY0 = {
    "items": [
        {
            "code": "pdf_margin_escape",
            "packages": ["pdf"],
            "message": "pg1: text runs 24.7 mm past the text block: 'this line runs far past the r…'",
            "page": 1,
            "box": [400.0, 484.1, 610.1, 494.1],
            "regionCount": 1,
            "overMm": 24.7,
        }
    ],
    "log": ["pdfcheck guard page=1 otsuEm=0.010 usedEm=0.1"],
}

# case -> (reason, the PARITY.md text it cites, the binary's exact {items, log}).
ACCEPTED = {
    "gap:n2_encrypted_skip": (
        "encrypted PDF: one skip note, no decryption (R82-DECODE); pdfminer decrypts it",
        "Encrypted PDFs are skipped, not decrypted",
        _ENCRYPTED_NOTE,
    ),
    "gap:n4_encrypted": (
        "encrypted PDF: one skip note, no decryption (R82-DECODE); pdfminer decrypts it",
        "Encrypted PDFs are skipped, not decrypted",
        _ENCRYPTED_NOTE,
    ),
    "gap:n4_lzw_early0": (
        "LZW /EarlyChange 0 is honoured, so the text is the Flate twin's; pdfminer ignores it",
        "honours `/EarlyChange 0`, which\n  pdfminer ignores",
        _LZW_EARLY0,
    ),
}


def _oracle():
    return oracle_or_skip()


def _binary():
    return binary_or_skip()


def _check(oracle, data, kwargs):
    result = oracle.check_pdf(data, page_budget=1e9, document_budget=1e9, **kwargs)
    return {"items": result.items, "log": list(result.log_lines)}


def _oracle_lines(oracle, data):
    """``[[page, text, box], ...]`` of the Python line grouping (scripts/py_dump.py)."""
    out = []
    for index, width, height, glyphs, paths, offpage in oracle.extract_pages(data):
        page = oracle._build_page(
            index, width, height, glyphs, paths, None, "", offpage, []
        )
        out.extend(
            [index, ln.text, [round(float(x), 1) for x in ln.box]] for ln in page.lines
        )
    return out


def _binary_lines(binary, pdf_path):
    done = subprocess.run(
        [binary, "--dump", *LIFTED, str(pdf_path)],
        capture_output=True,
        timeout=60,
        check=True,
    )
    out = []
    for row in done.stdout.decode("utf-8").splitlines():
        if row.strip():
            page = json.loads(row)
            out.extend([page["page"], text, box] for text, box in page["line_items"])
    return out


def _unmatched(left, right):
    """Lines of ``left`` with no line of ``right`` on the same page, same text, box within 0.5 pt."""
    pool = list(right)
    missing = []
    for page, text, box in left:
        hit = next(
            (
                n
                for n, (p, t, b) in enumerate(pool)
                if p == page
                and t == text
                and all(abs(x - y) <= 0.5 for x, y in zip(b, box))
            ),
            None,
        )
        if hit is None:
            missing.append([page, text, box])
        else:
            pool.pop(hit)
    return missing


def _assert_same(case, expected, got):
    assert case not in ACCEPTED
    assert item_diffs(expected["items"], got["items"]) == [], case
    assert got["log"] == expected["log"], case


def _assert_same_lines(case, py_lines, rust_lines):
    assert _unmatched(py_lines, rust_lines) == [], case
    assert _unmatched(rust_lines, py_lines) == [], case


def _sidecar(template="", blocks=None, marks=None, shell_pages=None, tex_pages=()):
    side = {
        "templateId": template,
        "blocks": {str(k): list(v) for k, v in (blocks or {}).items()},
        "shellPages": {str(k): v for k, v in (shell_pages or {}).items()},
        "texPages": sorted(tex_pages),
    }
    if marks is not None:
        side["marks"] = marks
    return side


# -- corpus: the 21 repository PDFs ----------------------------------------------------------------


def _corpus():
    return [
        line.strip()
        for line in CORPUS_LIST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_corpus_list_is_every_repository_pdf():
    found = sorted(
        str(p.relative_to(ROOT))
        for folder in ("examples", "samples", "tests/samples")
        for p in (ROOT / folder).rglob("*.pdf")
    )
    assert _corpus() == found and len(found) == 21


@pytest.mark.parametrize("name", _corpus())
def test_corpus_pdf_findings_and_lines(name, tmp_path):
    oracle, binary = _oracle(), _binary()
    path = ROOT / name
    data = path.read_bytes()
    side = _sidecar()
    _assert_same(
        f"corpus:{name}",
        _check(oracle, data, oracle_kwargs(side)),
        run_sidecar(binary, side, path, tmp_path),
    )
    _assert_same_lines(
        f"corpus:{name}", _oracle_lines(oracle, data), _binary_lines(binary, path)
    )


# -- synth: the constructed cases of the R81 tests -------------------------------------------------


def _synth_cases():
    from tests.colophon import test_pdf_layout_check_r81 as t

    B = t._BLOCK
    margin = t.text(72, 700, "short") + t.text(
        400, 680, "this line runs far past the right edge of the block"
    )
    node = "0.5 w 100 600 80 30 re S\n"
    stroke = "0.5 w 60 604 m 300 604 l S\n"
    label = t.text(100, 600, "Pressure")
    figure = "0.5 w 80 580 200 60 re S\n"
    gutter = t.text(100, 600, "Alpha", 10) + t.text(100 + 25.7 + 0.4, 600, "Beta", 8)
    stray = (
        t.body(5)
        + t.text(72, 500, "```python")
        + t.text(72, 440, "\\\\begin{figure} printed")
    )
    faulty = t.text(400, 680, "this line runs far past the right edge of the block")
    ten = "".join(
        t.text(400, 770 - 30 * n, "this line runs far past the right edge of the block")
        for n in range(14)
    )
    three = "".join(
        t.text(400, 700 - 12 * n, "this line runs far past the right edge of the block")
        for n in range(3)
    )
    guard = "".join(
        t.text(72, 700 - 14 * n, "aaaa bbbb cccc dddd eeee ffff gggg") for n in range(8)
    )
    one = {1: B}
    # name -> (pages or None for garbage bytes, template, blocks, tex pages, marks, shell pages)
    return {
        "clean_page": (
            [t.body() + t.text(400, 40, "1")],
            "fulldoc",
            one,
            (),
            None,
            None,
        ),
        "margin_escape": ([margin], "fulldoc", one, (), None, None),
        "margin_escape_noblock": ([margin], "fulldoc", {}, (), None, None),
        "caption_overlap": (
            [
                t.body(10)
                + t.text(72, 400, "Figure 1: the pump curve")
                + "0.5 g 60 395 200 40 re f\n"
            ],
            "fulldoc",
            one,
            (),
            None,
            None,
        ),
        "label_on_stroke": ([stroke + label], "fulldoc", one, (), None, None),
        "label_on_stroke_white_cover": (
            [stroke + "1 g 95 595 60 16 re f 0 g\n" + label],
            "fulldoc",
            one,
            (),
            None,
            None,
        ),
        "text_escapes_node": (
            [node + t.text(160, 610, "Overflow")],
            "fulldoc",
            one,
            (),
            None,
            None,
        ),
        "text_inside_node": (
            [node + t.text(105, 610, "Inside")],
            "fulldoc",
            one,
            (),
            None,
            None,
        ),
        "text_overlap": (
            [t.text(100, 600, "Alpha") + t.text(112, 600, "Beta")],
            "fulldoc",
            one,
            (),
            None,
            None,
        ),
        "text_overlap_extensible": (
            [t.text(100, 600, "---") + t.text(103, 600, "---")],
            "fulldoc",
            one,
            (),
            None,
            None,
        ),
        "label_gutter_sysml": ([figure + gutter], "sysml", one, (), None, None),
        "label_gutter_plots": ([figure + gutter], "plots", one, (), None, None),
        "stray_source_shell": ([stray], "document-shell", one, (), None, None),
        "stray_source_plots": ([stray], "plots", one, (), None, None),
        "empty_page_inside": (
            [t.text(72, 700, "two") + t.text(150, 700, "words"), t.body(), t.body()],
            "fulldoc",
            {1: B, 2: B, 3: B},
            (),
            None,
            None,
        ),
        "empty_page_drawn": (
            ["0.5 w 100 500 m 300 500 l S\n" + t.text(72, 700, "two words"), t.body()],
            "fulldoc",
            {1: B, 2: B},
            (),
            None,
            None,
        ),
        "empty_page_last_words": (
            [t.body(), t.text(72, 700, "two words")],
            "fulldoc",
            {1: B, 2: B},
            (),
            None,
            None,
        ),
        "empty_page_last_blank": (
            [t.body(), ""],
            "fulldoc",
            {1: B, 2: B},
            (),
            None,
            None,
        ),
        "warning_item": ([faulty], "fulldoc", one, (), None, None),
        "cap_at_ten": ([ten], "fulldoc", one, (), None, None),
        "dedupe_three": ([three], "fulldoc", one, (), None, None),
        "dedupe_tex_pages": ([three], "fulldoc", one, (1,), None, None),
        "offpage_dropped": (
            [t.body(5) + t.text(900, 400, "hidden") + t.text(-300, 400, "gone")],
            "fulldoc",
            one,
            (),
            None,
            None,
        ),
        "docstrum_guard": ([guard], "fulldoc", one, (), None, None),
        "budget_two_pages": (
            [faulty, t.body()],
            "fulldoc",
            {1: B, 2: B},
            (),
            None,
            None,
        ),
        "garbage": (None, "fulldoc", {}, (), None, None),
        "placement_marks_and_fence": (
            [faulty],
            "fulldoc",
            one,
            (),
            [["p1", "s", 1, 700.0, "p"], ["p1", "e", 1, 100.0, "p"]],
            {3: 1},
        ),
    }


_SYNTH_NAMES = [
    "clean_page",
    "margin_escape",
    "margin_escape_noblock",
    "caption_overlap",
    "label_on_stroke",
    "label_on_stroke_white_cover",
    "text_escapes_node",
    "text_inside_node",
    "text_overlap",
    "text_overlap_extensible",
    "label_gutter_sysml",
    "label_gutter_plots",
    "stray_source_shell",
    "stray_source_plots",
    "empty_page_inside",
    "empty_page_drawn",
    "empty_page_last_words",
    "empty_page_last_blank",
    "warning_item",
    "cap_at_ten",
    "dedupe_three",
    "dedupe_tex_pages",
    "offpage_dropped",
    "docstrum_guard",
    "budget_two_pages",
    "garbage",
    "placement_marks_and_fence",
]


@pytest.mark.parametrize("name", _SYNTH_NAMES)
def test_synth_case_findings(name, tmp_path):
    oracle, binary = _oracle(), _binary()
    from tests.colophon import test_pdf_layout_check_r81 as t

    pages, template, blocks, tex_pages, marks, shells = _synth_cases()[name]
    data = b"not a pdf" if pages is None else t.pdf(pages)
    path = tmp_path / f"{name}.pdf"
    path.write_bytes(data)
    side = _sidecar(template, blocks, marks, shells, tex_pages)
    _assert_same(
        f"synth:{name}",
        _check(oracle, data, oracle_kwargs(side)),
        run_sidecar(binary, side, path, tmp_path),
    )


def test_synth_names_cover_every_case():
    assert sorted(_SYNTH_NAMES) == sorted(_synth_cases())


# -- gap: the crate's gap fixtures -----------------------------------------------------------------


def _gap_manifest():
    return json.loads((GAP / "manifest.json").read_text(encoding="utf-8"))


def _gap_sidecar(entry):
    side = {
        "templateId": entry.get("template", ""),
        "blocks": entry.get("blocks", {}),
        "shellPages": entry.get("shellPages", {}),
        "texPages": entry.get("texPages", []),
    }
    if entry.get("template") == "fulldoc":
        side["marks"] = entry.get("marks", [])
    return side


@pytest.mark.parametrize(
    "entry",
    [e for e in _gap_manifest() if f"gap:{e['name']}" not in ACCEPTED],
    ids=lambda e: e["name"],
)
def test_gap_fixture_findings(entry, tmp_path):
    oracle, binary = _oracle(), _binary()
    case = f"gap:{entry['name']}"
    path = GAP / entry["pdf"]
    data = path.read_bytes()
    side = _gap_sidecar(entry)
    _assert_same(
        case,
        _check(oracle, data, oracle_kwargs(side)),
        run_sidecar(binary, side, path, tmp_path),
    )
    if entry["compare"] == "both":
        _assert_same_lines(
            case, _oracle_lines(oracle, data), _binary_lines(binary, path)
        )


# -- real: worker output with the sidecars sandbox_render writes -----------------------------------


@pytest.mark.parametrize("name", real_samples())
def test_real_sample_findings_and_lines(name, tmp_path):
    oracle, binary = _oracle(), _binary()
    folder = REAL / name
    side = json.loads((folder / "sidecar.json").read_text(encoding="utf-8"))
    data = (folder / "out.pdf").read_bytes()
    expected = _check(oracle, data, oracle_kwargs(side))
    # The recorded in-image Python run agrees with this oracle run.
    recorded = json.loads((folder / "python-lifted.json").read_text(encoding="utf-8"))
    assert (
        item_diffs(recorded["items"], expected["items"], tolerance=0.0) == []
        and recorded["log"] == expected["log"]
    )
    _assert_same(
        f"real:{name}",
        expected,
        run_sidecar(binary, side, folder / "out.pdf", tmp_path),
    )
    _assert_same_lines(
        f"real:{name}",
        _oracle_lines(oracle, data),
        _binary_lines(binary, folder / "out.pdf"),
    )


def test_real_samples_cover_every_kind_and_the_cjk_languages():
    names = set(real_samples())
    assert {
        "sysml-interconnection",
        "fulldoc-two-parts",
        "fulldoc-overhang",
        "shell-label-on-stroke",
    } <= names
    assert {"shell-zh-tw", "shell-zh-cn", "shell-ko", "shell-ja"} <= names
    assert len(names) == 15


# -- the accepted divergences ----------------------------------------------------------------------


def _accepted_cases():
    return sorted(ACCEPTED)


@pytest.mark.parametrize("case", _accepted_cases())
def test_accepted_divergences(case, tmp_path):
    """Each is a PARITY.md line, still differs from the oracle, and the binary gives exactly the pinned output."""
    oracle, binary = _oracle(), _binary()
    reason, parity_text, pinned = ACCEPTED[case]
    assert reason and parity_text in (CRATE / "PARITY.md").read_text(encoding="utf-8")
    group, name = case.split(":", 1)
    assert group == "gap"
    (entry,) = [e for e in _gap_manifest() if e["name"] == name]
    path = GAP / entry["pdf"]
    side = _gap_sidecar(entry)
    got = run_sidecar(binary, side, path, tmp_path)
    assert got == pinned
    py = _check(oracle, path.read_bytes(), oracle_kwargs(side))
    assert (
        item_diffs(py["items"], got["items"]) != [] or py["log"] != got["log"]
    ), "no longer diverges: drop it"


def test_accepted_divergences_are_the_known_list():
    assert len(ACCEPTED) == 3
    assert {case.split(":")[1] for case in ACCEPTED} == {
        "n2_encrypted_skip",
        "n4_encrypted",
        "n4_lzw_early0",
    }


def test_parity_corpus_files_exist():
    assert CORPUS_LIST.is_file() and all((ROOT / name).is_file() for name in _corpus())
    assert all((GAP / e["pdf"]).is_file() for e in _gap_manifest())
    assert all(Path(REAL / n / "sidecar.json").is_file() for n in real_samples())
