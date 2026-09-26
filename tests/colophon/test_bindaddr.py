# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from colophon.bindaddr import BindError, validate_bind_address
from colophon.config import ConfigError, load_config


def _env(**overrides):
    base = {
        "COLOPHON_BIND_ADDRESS": "192.0.2.10",
        "COLOPHON_WORKER_TOKEN": "test-token-value",
        "COLOPHON_KILL_SWITCH_FILE": "/var/lib/colophon/kill-switch",
        "COLOPHON_IMAGE": "colophon-render:local",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "address,reason",
    [
        (None, "unset"),
        ("", "unset"),
        ("   ", "unset"),
        ("0.0.0.0", "unspecified"),
        ("::", "unspecified"),
        ("10.1.2.3", "lan"),
        ("172.16.0.5", "lan"),
        ("172.31.255.1", "lan"),
        ("192.168.1.10", "lan"),
        ("169.254.1.1", "lan"),
        ("fe80::1", "lan"),
        ("fd00::1", "lan"),
        ("127.0.0.1", "lan"),
        ("::1", "lan"),
        ("not-an-ip", "invalid"),
        ("worker.example", "invalid"),
    ],
)
def test_bind_address_refused(address, reason):
    with pytest.raises(BindError) as caught:
        validate_bind_address(address)
    assert caught.value.reason == reason


@pytest.mark.parametrize(
    "address",
    ["192.0.2.1", "198.51.100.20", "203.0.113.5", "2001:db8::1"],
)
def test_configured_unicast_address_accepted(address):
    assert validate_bind_address(address) == address


def test_config_refuses_unset_address():
    env = _env()
    del env["COLOPHON_BIND_ADDRESS"]
    with pytest.raises(ConfigError, match="COLOPHON_BIND_ADDRESS"):
        load_config(env)


def test_config_refuses_unspecified_and_lan():
    with pytest.raises(ConfigError, match="unspecified"):
        load_config(_env(COLOPHON_BIND_ADDRESS="0.0.0.0"))
    with pytest.raises(ConfigError, match="lan"):
        load_config(_env(COLOPHON_BIND_ADDRESS="192.168.0.20"))


def test_config_refuses_docker_runtime():
    with pytest.raises(ConfigError, match="podman"):
        load_config(_env(COLOPHON_PODMAN="docker"))


def test_config_refuses_blank_token():
    with pytest.raises(ConfigError, match="COLOPHON_WORKER_TOKEN"):
        load_config(_env(COLOPHON_WORKER_TOKEN=""))
