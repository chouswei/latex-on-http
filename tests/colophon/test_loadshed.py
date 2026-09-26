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
    assert body["reason"] == "loadavg"
    assert supervisor.busy() is False


def test_host_load_report_shape(client, auth):
    response = client.get("/v1/host-load", headers=auth)
    assert response.status_code == 200
    body = response.get_json()
    assert body["loadAvg1m"] == 0.2
    assert body["memAvailableMiB"] == 8192
    assert body["busy"] is False
    assert body["stale"] is False
    assert body["intervalSec"] == 10
