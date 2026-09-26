# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from colophon.limits import (
    LOAD_AVG_1M_THRESHOLD,
    MEM_AVAILABLE_MIB_THRESHOLD,
    REPORT_MAX_AGE_SEC,
)
from colophon.load import LoadMonitor, shed_reason
from colophon.worker import create_app
from colophon.killswitch import KillSwitch
from tests.colophon.conftest import valid_body


def test_thresholds_accept_exact_bounds():
    assert (
        shed_reason(LOAD_AVG_1M_THRESHOLD, MEM_AVAILABLE_MIB_THRESHOLD, age_sec=0)
        is None
    )


def test_loadavg_above_threshold_sheds():
    assert shed_reason(3.01, MEM_AVAILABLE_MIB_THRESHOLD, age_sec=0) == "loadavg"


def test_memory_below_threshold_sheds():
    assert shed_reason(0.1, MEM_AVAILABLE_MIB_THRESHOLD - 1, age_sec=0) == "mem"


def test_stale_report_sheds():
    assert shed_reason(0.1, 8000, age_sec=REPORT_MAX_AGE_SEC) is None
    assert shed_reason(0.1, 8000, age_sec=REPORT_MAX_AGE_SEC + 1) == "stale"
    assert shed_reason(0.1, 8000, age_sec=None) == "stale"


def test_unreadable_sample_sheds():
    def boom():
        raise OSError("meminfo")

    monitor = LoadMonitor(reader=boom)
    monitor.sample()
    assert monitor.decision() == "unreadable"


def test_http_load_shed(config, switch_path, supervisor, auth):
    monitor = LoadMonitor(reader=lambda: (3.5, 8192))
    monitor.sample()
    app = create_app(config, KillSwitch(switch_path), monitor, supervisor)
    client = app.test_client()
    response = client.post("/v1/jobs", json=valid_body(), headers=auth)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "10"
    body = response.get_json()
    assert body["error"] == "rejectLoadShed"
    assert body["result"] == "refused"
    assert body["reason"] == "loadavg"
    assert set(body["load"]) == {
        "loadavg",
        "memAvailableMiB",
        "activeJobs",
        "queued",
        "reportedAt",
    }
    assert body["load"]["loadavg"] == 3.5
    assert body["load"]["activeJobs"] == 0
    assert body["load"]["queued"] == 0
    assert supervisor.busy() is False


_HOST_LOAD_KEYS = {
    "loadavg",
    "memAvailableMiB",
    "activeJobs",
    "queued",
    "reportedAt",
}


def _assert_reported_at(value):
    from datetime import datetime, timedelta

    observed = datetime.fromisoformat(value)
    assert observed.tzinfo is not None
    assert observed.utcoffset() == timedelta(0)


def test_host_load_report_shape(client, auth):
    response = client.get("/v1/host-load", headers=auth)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert set(body) == _HOST_LOAD_KEYS
    assert body["loadavg"] == 0.2
    assert isinstance(body["loadavg"], float)
    assert body["memAvailableMiB"] == 8192
    assert body["activeJobs"] == 0
    assert body["queued"] == 0
    _assert_reported_at(body["reportedAt"])


def test_host_load_requires_the_worker_token(client):
    response = client.get("/v1/host-load")
    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}


def test_load_path_is_not_an_alias(client, auth):
    response = client.get("/load", headers=auth)
    assert response.status_code == 404


def test_host_load_when_memory_is_under_the_threshold(
    config, switch_path, supervisor, auth
):
    monitor = LoadMonitor(reader=lambda: (0.2, 4095))
    monitor.sample()
    app = create_app(config, KillSwitch(switch_path), monitor, supervisor)
    client = app.test_client()
    response = client.get("/v1/host-load", headers=auth)
    assert response.status_code == 200
    body = response.get_json()
    assert body["memAvailableMiB"] == 4095
    assert body["activeJobs"] == 0
    assert body["queued"] == 0
    refused = client.post("/v1/jobs", json=valid_body(), headers=auth)
    assert refused.status_code == 429
    refused_body = refused.get_json()
    assert refused_body["error"] == "rejectLoadShed"
    assert refused_body["reason"] == "mem"
    assert set(refused_body["load"]) == _HOST_LOAD_KEYS
    assert refused_body["load"]["activeJobs"] == 0
    assert refused_body["load"]["queued"] == 0
    assert refused_body["load"]["memAvailableMiB"] == 4095


def test_host_load_reports_the_running_job_and_an_empty_queue(client, auth, supervisor):
    supervisor._busy.acquire()
    try:
        response = client.get("/v1/host-load", headers=auth)
    finally:
        supervisor._busy.release()
    body = response.get_json()
    assert response.status_code == 200
    assert body["activeJobs"] == 1
    assert body["queued"] == 0


def test_unreadable_host_load_is_503(config, switch_path, supervisor, auth):
    def boom():
        raise OSError("meminfo")

    monitor = LoadMonitor(reader=boom)
    monitor.sample()
    app = create_app(config, KillSwitch(switch_path), monitor, supervisor)
    response = app.test_client().get("/v1/host-load", headers=auth)
    assert response.status_code == 503
    body = response.get_json()
    assert set(body) == _HOST_LOAD_KEYS
    assert body["loadavg"] is None
    assert body["memAvailableMiB"] is None
    assert body["activeJobs"] == 0
    assert body["queued"] == 0
    _assert_reported_at(body["reportedAt"])


def test_stale_host_load_stays_200(config, switch_path, supervisor, auth):
    now = {"t": 1000.0}
    monitor = LoadMonitor(reader=lambda: (0.2, 8192), clock=lambda: now["t"])
    monitor.sample()
    now["t"] = 1000.0 + REPORT_MAX_AGE_SEC + 1
    app = create_app(config, KillSwitch(switch_path), monitor, supervisor)
    client = app.test_client()
    response = client.get("/v1/host-load", headers=auth)
    assert response.status_code == 200
    assert response.get_json()["loadavg"] == 0.2
    refused = client.post("/v1/jobs", json=valid_body(), headers=auth)
    assert refused.status_code == 429
    assert refused.get_json()["reason"] == "stale"
