# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import hashlib
from pathlib import Path

import pytest

from colophon.limits import limits_payload
from colophon.revision import package_set, package_set_hash, source_url, version_payload

PACKAGE_SET_SOURCE = (
    Path(__file__).resolve().parents[2] / "colophon" / "package_set.txt"
)

# Widened set from commits 19de0c2 and 5e07aef: circuitikz through pgfgantt,
# plus endleaf-floorplan. The digest is sha256 of these names joined by
# newlines, with no trailing newline.
WIDENED_PACKAGE_SET = [
    "bytefield",
    "chemfig",
    "circuitikz",
    "endleaf-floorplan",
    "forest",
    "mhchem",
    "pgf",
    "pgfgantt",
    "pgfplots",
    "siunitx",
    "tikz-3dplot",
    "tikz-cd",
    "tikz-dimline",
    "tikz-feynman",
    "tikz-timing",
    "tikzscale",
]
WIDENED_PACKAGE_SET_HASH = (
    "f2946ed8f9682cc0e0dffa468d29fdc25ae2feb85e7d9d1291414dc1cf2a310d"
)


def test_version_requires_token(client):
    response = client.get("/version")
    assert response.status_code == 401


def test_version_returns_baked_commit(client, auth, monkeypatch):
    monkeypatch.setenv("ENDLEAF_GIT_COMMIT", "0123456789abcdef0123456789abcdef01234567")
    response = client.get("/version", headers=auth)
    assert response.status_code == 200
    body = response.get_json()
    assert body["version"]
    assert body["commit"] == "0123456789abcdef0123456789abcdef01234567"
    assert body["source"].endswith("/commit/" + body["commit"])
    assert response.headers["Cache-Control"] == "no-store"


def test_missing_revision_is_unknown(monkeypatch):
    monkeypatch.delenv("ENDLEAF_GIT_COMMIT", raising=False)
    monkeypatch.delenv("COLOPHON_GIT_COMMIT", raising=False)
    monkeypatch.setattr("colophon.revision._read_baked_file", lambda: "")
    body = version_payload()
    assert body["commit"] == "unknown"
    assert body["source"].startswith("https://github.com/chouswei/latex-on-http")
    assert "/commit/" not in body["source"]


def test_widened_package_set_hash_is_pinned():
    assert package_set() == WIDENED_PACKAGE_SET
    assert package_set_hash(WIDENED_PACKAGE_SET) == WIDENED_PACKAGE_SET_HASH


def test_deprecated_git_commit_env(monkeypatch, caplog):
    import logging

    monkeypatch.delenv("ENDLEAF_GIT_COMMIT", raising=False)
    monkeypatch.setenv("COLOPHON_GIT_COMMIT", "abc1234")
    with caplog.at_level(logging.WARNING):
        body = version_payload()
    assert body["commit"] == "abc1234"
    assert (
        "deprecated environment variable COLOPHON_GIT_COMMIT; set ENDLEAF_GIT_COMMIT"
        in caplog.text
    )


def test_version_package_set_is_sorted_and_hashed(client, auth, monkeypatch):
    monkeypatch.delenv("ENDLEAF_GIT_COMMIT", raising=False)
    monkeypatch.delenv("COLOPHON_GIT_COMMIT", raising=False)
    response = client.get("/version", headers=auth)
    assert response.status_code == 200
    body = response.get_json()
    names = package_set()
    assert "endleaf-floorplan" in names
    assert names == sorted(names)
    assert body["packageSet"] == names
    digest = hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()
    assert body["packageSetHash"] == digest
    assert digest == package_set_hash(names)
    assert not digest.endswith("\n")
    source = [
        line.strip()
        for line in PACKAGE_SET_SOURCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert names == source
    assert body["limits"] == limits_payload()


def test_version_limits_name_the_worker_caps():
    limits = limits_payload()
    assert limits == {
        "cpu": 1,
        "memMiB": 2048,
        "wallSec": 60,
        "outputMiB": 20,
        "pidsMax": 256,
        "tmpfsMiB": 512,
        "inputMiB": 16,
        "maxFencesPerJob": 5,
        "retryAfterSec": 10,
    }


def test_baked_package_set_file_is_what_version_reads(tmp_path, monkeypatch):
    baked = tmp_path / "PACKAGE_SET"
    baked.write_text("siunitx\ncircuitikz\n", encoding="utf-8")
    monkeypatch.setattr("colophon.revision._package_set_file", lambda: baked)
    body = version_payload()
    assert body["packageSet"] == ["circuitikz", "siunitx"]
    assert body["packageSetHash"] == hashlib.sha256(b"circuitikz\nsiunitx").hexdigest()


@pytest.mark.parametrize(
    "commit,suffix",
    [
        ("abc1234", "/commit/abc1234"),
        ("v1.2.3", "/tree/v1.2.3"),
        ("unknown", ""),
    ],
)
def test_source_url(commit, suffix):
    url = source_url(commit)
    assert url.startswith("https://github.com/chouswei/latex-on-http")
    if suffix:
        assert url.endswith(suffix)
    else:
        assert url.endswith("latex-on-http")
