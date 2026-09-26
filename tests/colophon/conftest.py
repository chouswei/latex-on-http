# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from colophon.config import load_config
from colophon.killswitch import KillSwitch
from colophon.load import LoadMonitor
from colophon.runner import Outcome, Supervisor
from colophon.worker import create_app

TOKEN = "test-token-value"


def valid_body(**overrides):
    body = {
        "input": "Hello",
        "inputKind": "markdown",
        "outputFormat": "pdf",
        "lane": "InstruMeasure",
    }
    body.update(overrides)
    return body


class _Runner:
    def __init__(self, outcome=None):
        self.calls = []
        self.outcome = outcome or Outcome(
            kind="ok", body=b"%PDF-1.4", content_type="application/pdf"
        )

    def __call__(self, job, name, abort_event):
        self.calls.append(job)
        return self.outcome


@pytest.fixture
def switch_path(tmp_path):
    path = tmp_path / "kill-switch"
    path.write_text("clear\n", encoding="utf-8")
    return path


@pytest.fixture
def config(switch_path):
    return load_config(
        {
            "COLOPHON_BIND_ADDRESS": "100.64.0.1",
            "COLOPHON_BIND_ALLOWED_CIDR": "100.64.0.0/10",
            "COLOPHON_WORKER_TOKEN": TOKEN,
            "COLOPHON_KILL_SWITCH_FILE": str(switch_path),
            "COLOPHON_IMAGE": "colophon-render:local",
        }
    )


@pytest.fixture
def runner():
    return _Runner()


@pytest.fixture
def monitor():
    mon = LoadMonitor(reader=lambda: (0.2, 8192))
    mon.sample()
    return mon


@pytest.fixture
def supervisor(runner):
    return Supervisor(runner, retry_after_sec=10)


@pytest.fixture
def client(config, switch_path, monitor, supervisor):
    switch = KillSwitch(switch_path)
    app = create_app(config, switch, monitor, supervisor)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}
