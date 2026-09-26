# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from colophon.revision import source_url, version_payload


def test_version_requires_token(client):
    response = client.get("/version")
    assert response.status_code == 401


def test_version_returns_baked_commit(client, auth, monkeypatch):
    monkeypatch.setenv(
        "COLOPHON_GIT_COMMIT", "0123456789abcdef0123456789abcdef01234567"
    )
    response = client.get("/version", headers=auth)
    assert response.status_code == 200
    body = response.get_json()
    assert body["version"]
    assert body["commit"] == "0123456789abcdef0123456789abcdef01234567"
    assert body["source"].endswith("/commit/" + body["commit"])
    assert response.headers["Cache-Control"] == "no-store"


def test_missing_revision_is_unknown(monkeypatch):
    monkeypatch.delenv("COLOPHON_GIT_COMMIT", raising=False)
    monkeypatch.setattr("colophon.revision._read_baked_file", lambda: "")
    body = version_payload()
    assert body["commit"] == "unknown"
    assert body["source"].startswith("https://github.com/chouswei/latex-on-http")
    assert "/commit/" not in body["source"]


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
