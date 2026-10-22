# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

import colophon.enums
import colophon.render_plan
from colophon.config import load_config
from colophon.killswitch import KillSwitch
from colophon.load import LoadMonitor
from colophon.runner import Outcome, Supervisor
from colophon.worker import create_app
from tests.colophon.lanes import LANE_A, PLACEHOLDER_LANES, PROD_LANES, TEMPLATE_LANE

TOKEN = "test-token-value"


def valid_body(**overrides):
    body = {
        "body": "Hello",
        "templateId": "document-shell",
        "outputFormat": "pdf",
        "lane": LANE_A,
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def placeholder_lanes(request, monkeypatch):
    """Test-only: accept lane-a/lane-b next to the production lanes.

    Production code is untouched. colophon.enums.LANES is patched for the
    test's duration, and the placeholders map to an existing lane's template
    folder in the render plan. Tests marked ``real_lanes`` see the
    unpatched production list.
    """
    if request.node.get_closest_marker("real_lanes"):
        return
    monkeypatch.setattr(colophon.enums, "LANES", PROD_LANES + PLACEHOLDER_LANES)
    template = colophon.render_plan._template
    monkeypatch.setattr(
        colophon.render_plan,
        "_template",
        lambda lane, name: template(TEMPLATE_LANE.get(lane, lane), name),
    )


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
            "ENDLEAF_BIND_ADDRESS": "100.64.0.1",
            "ENDLEAF_BIND_ALLOWED_CIDR": "100.64.0.0/10",
            "ENDLEAF_WORKER_TOKEN": TOKEN,
            "ENDLEAF_KILL_SWITCH_FILE": str(switch_path),
            "ENDLEAF_IMAGE": "endleaf-render:local",
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
