"""ENDLEAF-R82-IMPL / -IFACE: the image's wire-contract module equals the Python reference.

colophon/pdf_layout_wire.py is what the worker image ships around the Rust binary;
colophon/pdf_layout_check.py is the test/CI-only reference oracle and is kept out of the
image. These tests pin the two together and keep the oracle out of the worker's imports.
"""

import ast
import json
from pathlib import Path

from colophon import pdf_layout_check as oracle
from colophon import pdf_layout_wire as wire

ROOT = Path(__file__).resolve().parents[2]


def test_constants_equal_the_oracle():
    for name in ("PDF_PREFIX", "PDF_LOG_PREFIX", "PACKAGES", "SKIP_CODE", "MORE_CODE", "CODES"):
        assert getattr(wire, name) == getattr(oracle, name), name
    assert wire._ITEM_KEYS == oracle._ITEM_KEYS


_ITEMS = [
    {"code": "pdf_margin_escape", "packages": ["pdf"], "message": "m", "page": 2,
     "box": [1.0, 2.0, 3.0, 4.0], "overMm": 1.8},
    {"code": "pdf_label_on_stroke", "packages": ["pdf"], "message": "l", "page": 1,
     "partId": "p4", "fenceNumber": 3, "regionCount": 2},
    {"code": "pdf_more_findings", "packages": ["pdf"], "message": "more", "count": 4},
]


def test_layout_line_equals_the_oracle():
    assert wire.pdf_layout_line([]) is None and oracle.pdf_layout_line([]) is None
    assert wire.pdf_layout_line(_ITEMS) == oracle.pdf_layout_line(_ITEMS)


def test_parse_equals_the_oracle_on_good_and_bad_lines():
    good = oracle.pdf_layout_line(_ITEMS)
    cases = [
        None, b"", "", good, good.encode(), "noise\n" + good + "\nmore",
        "ENDLEAF_PDFLAYOUT not json", "ENDLEAF_PDFLAYOUT {}",
        "ENDLEAF_PDFLAYOUT " + json.dumps([{"code": "nope", "packages": ["pdf"], "message": "x"}]),
        "ENDLEAF_PDFLAYOUT " + json.dumps([{**_ITEMS[0], "page": True, "box": [1, 2, 3]}]),
        "ENDLEAF_PDFLAYOUT " + json.dumps([{**_ITEMS[1], "fenceNumber": "3"}]),
    ]
    for case in cases:
        assert wire.parse_pdf_layout(case) == oracle.parse_pdf_layout(case), case


def _imports(path):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_worker_modules_do_not_import_the_oracle():
    for path in sorted((ROOT / "colophon").glob("*.py")):
        if path.name == "pdf_layout_check.py":
            continue
        assert "colophon.pdf_layout_check" not in _imports(path.relative_to(ROOT)), path.name


def test_oracle_is_kept_out_of_the_image_build_context():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "colophon/pdf_layout_check.py" in ignored
    assert "__pycache__" in ignored and "rust/*/target/" in ignored
