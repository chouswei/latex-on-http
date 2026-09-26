# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from colophon.killswitch import KillSwitch
from colophon.worker import create_app
from tests.colophon.conftest import valid_body


def test_missing_switch_file_is_engaged(tmp_path):
    switch = KillSwitch(tmp_path / "absent")
    state = switch.read()
    assert state.readable is False
    assert state.engaged is True
    assert state.blocks_jobs is True


def test_garbage_switch_is_engaged(tmp_path):
    path = tmp_path / "switch"
    path.write_text("maybe\n", encoding="utf-8")
    state = KillSwitch(path).read()
    assert state.readable is False
    assert state.engaged is True


def test_http_refuses_when_switch_unreadable(
    config, monitor, supervisor, auth, tmp_path
):
    missing = tmp_path / "nope"
    app = create_app(config, KillSwitch(missing), monitor, supervisor)
    response = app.test_client().post("/v1/jobs", json=valid_body(), headers=auth)
    assert response.status_code == 403
    body = response.get_json()
    assert body["error"] == "rejectKillSwitch"
    assert body["readable"] is False
    assert body["engaged"] is True
    assert supervisor.busy() is False


def test_clear_switch_allows_a_job(client, auth):
    response = client.post("/v1/jobs", json=valid_body(), headers=auth)
    assert response.status_code == 200
    assert response.headers["X-Colophon-Result"] == "ok"
    assert response.headers["Cache-Control"] == "no-store"
