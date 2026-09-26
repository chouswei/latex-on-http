# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Revision baked at build time, for GET /version."""

import os
import re
from pathlib import Path

from colophon import __version__

SOURCE_REPOSITORY = "https://github.com/chouswei/latex-on-http"
_SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")
_TAG = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")


def _read_baked_file():
    path = Path(__file__).with_name("GIT_COMMIT")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return text.strip()


def revision():
    """Return the build commit or tag, or ``unknown`` when it was not baked."""
    raw = os.environ.get("COLOPHON_GIT_COMMIT", "").strip()
    if not raw:
        raw = _read_baked_file()
    if not raw or raw == "unknown":
        return "unknown"
    if any(ch.isspace() for ch in raw):
        return "unknown"
    if not (_SHA.fullmatch(raw) or _TAG.fullmatch(raw)):
        return "unknown"
    return raw


def source_url(commit):
    if _SHA.fullmatch(commit or ""):
        return f"{SOURCE_REPOSITORY}/commit/{commit}"
    if commit and commit != "unknown" and _TAG.fullmatch(commit):
        return f"{SOURCE_REPOSITORY}/tree/{commit}"
    return SOURCE_REPOSITORY


def version_payload():
    commit = revision()
    return {
        "version": __version__,
        "commit": commit,
        "source": source_url(commit),
    }
