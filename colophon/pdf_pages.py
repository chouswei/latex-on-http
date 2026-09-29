# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Page count for the fulldoc cap. No shell and no poppler."""

import re

from colophon.limits import FULLDOC_MAX_PAGES

# XeLaTeX: "Output written on job.pdf (3 pages, 12345 bytes)."
_LOG_PAGES = re.compile(r"Output written on \S+ \((\d+) page")
# xdvipdfmx writes one /Type /Page object per page. /Type /Pages is the tree.
_PDF_PAGE = re.compile(rb"/Type\s*/Page(?!s)\b")


def pages_from_log(log):
    """Last ``Output written`` count, or ``None`` when the log has none."""
    if not log:
        return None
    found = _LOG_PAGES.findall(log)
    if not found:
        return None
    return int(found[-1])


def pages_from_pdf(data):
    """Count page objects. ``None`` when the bytes are not a PDF or have none."""
    if not isinstance(data, (bytes, bytearray)) or not data.startswith(b"%PDF"):
        return None
    count = len(_PDF_PAGE.findall(data))
    if count < 1:
        return None
    return count


def fulldoc_page_count(data, log):
    """Prefer the engine log. The PDF scan is the fallback."""
    logged = pages_from_log(log)
    if logged is not None:
        return logged
    return pages_from_pdf(data)


def fulldoc_page_failure(pages):
    """A message when ``pages`` is over the cap or unreadable. ``None`` when it is in range."""
    if pages is None:
        return "fulldoc page count is unreadable"
    if pages > FULLDOC_MAX_PAGES:
        return f"fulldoc exceeds maxPages {FULLDOC_MAX_PAGES} (got {pages} pages)"
    return None
