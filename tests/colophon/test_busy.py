# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from tests.colophon.conftest import valid_body


def test_busy_refuses_immediately(client, supervisor, runner, auth):
    assert supervisor._busy.acquire(blocking=False)
    try:
        response = client.post("/v1/jobs", json=valid_body(), headers=auth)
    finally:
        supervisor._busy.release()
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "10"
    assert response.get_json()["error"] == "rejectBusy"
    assert runner.calls == []


def test_abort_while_idle(client, auth):
    response = client.post("/v1/jobs/abort", headers=auth)
    assert response.status_code == 404
    assert response.get_json() == {"aborted": False, "error": "idle"}


def test_missing_token_is_unauthorized(client):
    response = client.post("/v1/jobs", json=valid_body())
    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"
