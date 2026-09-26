# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Revision baked at build time, for GET /version."""

import hashlib
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


def _package_set_file():
    """Prefer the file the image build writes. Tests use the source list."""
    baked = Path(__file__).with_name("PACKAGE_SET")
    if baked.is_file():
        return baked
    return Path(__file__).with_name("package_set.txt")


def package_set():
    """Sorted TeX package names. Read from the baked file; no shell."""
    text = _package_set_file().read_text(encoding="utf-8")
    names = [line.strip() for line in text.splitlines() if line.strip()]
    if len(names) != len(set(names)):
        raise ValueError("package set has duplicate names")
    return sorted(names)


def package_set_hash(names):
    """SHA-256 of the sorted names joined by newlines, with no trailing newline."""
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def version_payload():
    commit = revision()
    names = package_set()
    return {
        "version": __version__,
        "commit": commit,
        "source": source_url(commit),
        "packageSet": names,
        "packageSetHash": package_set_hash(names),
    }
