"""ENDLEAF-R82-IFACE: the worker's ENDLEAF_PDFLAYOUT / ENDLEAF_PDFLOG wire contract (stdlib only).

The PDF layout checker in the image is the Rust binary ``endleaf-pdfcheck``. This module
holds only what the worker needs around it: the line prefixes, the codes, writing the one
ENDLEAF_PDFLAYOUT line and reading it back. It is a verbatim copy of those parts of
``colophon/pdf_layout_check.py``, the Python reference implementation (oracle), which is
used in tests and CI only and is not shipped in the image (.dockerignore).
tests/colophon/test_pdf_layout_wire_r82.py pins this module to the oracle.
"""

import json

PDF_PREFIX = "ENDLEAF_PDFLAYOUT "
PDF_LOG_PREFIX = "ENDLEAF_PDFLOG "
PACKAGES = ["pdf"]
SKIP_CODE = "pdf_check_skipped"
MORE_CODE = "pdf_more_findings"
CODES = (
    "pdf_margin_escape",
    "pdf_caption_overlap",
    "pdf_label_on_stroke",
    "pdf_text_escapes_node",
    "pdf_text_overlap",
    "pdf_label_gutter",
    "pdf_stray_source",
    "pdf_empty_page",
)


def pdf_layout_line(items):
    """One stderr line, or ``None`` when there is nothing to report."""
    if not items:
        return None
    return PDF_PREFIX + json.dumps(items, separators=(",", ":"))


_ITEM_KEYS = {
    "page": int,
    "overMm": (int, float),
    "regionCount": int,
    "partId": str,
    "fenceNumber": int,
    "count": int,
}


def parse_pdf_layout(stderr):
    """Read the ``ENDLEAF_PDFLAYOUT`` line back; ``[]`` when absent or malformed."""
    if not stderr:
        return []
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    for line in text.splitlines():
        if not line.startswith(PDF_PREFIX):
            continue
        try:
            parsed = json.loads(line[len(PDF_PREFIX) :])
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        clean = []
        for item in parsed:
            if (
                isinstance(item, dict)
                and item.get("code") in (*CODES, SKIP_CODE, MORE_CODE)
                and item.get("packages") == PACKAGES
                and isinstance(item.get("message"), str)
                and item["message"]
            ):
                kept = {
                    "code": item["code"],
                    "packages": list(PACKAGES),
                    "message": item["message"],
                }
                for key, kind in _ITEM_KEYS.items():
                    if (
                        key in item
                        and isinstance(item[key], kind)
                        and not isinstance(item[key], bool)
                    ):
                        kept[key] = item[key]
                box = item.get("box")
                if (
                    isinstance(box, list)
                    and len(box) == 4
                    and all(
                        isinstance(x, (int, float)) and not isinstance(x, bool)
                        for x in box
                    )
                ):
                    kept["box"] = list(box)
                clean.append(kept)
        return clean
    return []
