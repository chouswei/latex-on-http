# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from colophon.bindaddr import BindError, validate_bind_address
from colophon.config import ConfigError, load_config

# Example overlay ranges. 100.64.0.0/10 is CGNAT; fd7a:115c:a1e0::/48 is a
# unique-local prefix of the same kind operators often use for an overlay.
_CGNAT = "100.64.0.0/10"
_ULA = "fd7a:115c:a1e0::/48"


def _env(**overrides):
    base = {
        "COLOPHON_BIND_ADDRESS": "100.64.0.1",
        "COLOPHON_BIND_ALLOWED_CIDR": _CGNAT,
        "COLOPHON_WORKER_TOKEN": "test-token-value",
        "COLOPHON_KILL_SWITCH_FILE": "/var/lib/colophon/kill-switch",
        "COLOPHON_IMAGE": "colophon-render:local",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "address,cidr,reason",
    [
        (None, _CGNAT, "unset"),
        ("", _CGNAT, "unset"),
        ("   ", _CGNAT, "unset"),
        ("0.0.0.0", _CGNAT, "unspecified"),
        ("::", _ULA, "unspecified"),
        ("10.1.2.3", "0.0.0.0/0", "lan"),
        ("172.16.0.5", "0.0.0.0/0", "lan"),
        ("172.31.255.1", "172.16.0.0/12", "lan"),
        ("192.168.1.10", "0.0.0.0/0", "lan"),
        ("169.254.1.1", "0.0.0.0/0", "lan"),
        ("fe80::1", "::/0", "lan"),
        ("127.0.0.1", "0.0.0.0/0", "lan"),
        ("::1", "::/0", "lan"),
        ("224.0.0.1", "0.0.0.0/0", "lan"),
        ("not-an-ip", _CGNAT, "invalid"),
        ("worker.example", _CGNAT, "invalid"),
        # 192.88.99.0/24 is the deprecated 6to4 anycast block. ipaddress marks
        # it is_global, unlike the RFC 5737 documentation ranges.
        ("192.88.99.1", "192.88.99.0/24", "global"),
        ("192.88.99.1", "0.0.0.0/0", "global"),
        ("100.64.0.1", "192.0.2.0/24", "cidr"),
        ("100.64.0.1", "100.65.0.0/16", "cidr"),
        ("fd7a:115c:a1e0::1", _CGNAT, "cidr"),
        ("fd00::1", _ULA, "cidr"),
        ("100.64.0.1", None, "cidr_unset"),
        ("100.64.0.1", "", "cidr_unset"),
        ("100.64.0.1", "100.64.0.1/10", "cidr_invalid"),
    ],
)
def test_bind_address_refused(address, cidr, reason):
    with pytest.raises(BindError) as caught:
        validate_bind_address(address, cidr)
    assert caught.value.reason == reason


@pytest.mark.parametrize(
    "address,cidr",
    [
        ("100.64.0.1", _CGNAT),
        ("100.64.1.2", _CGNAT),
        ("100.127.255.254", _CGNAT),
        ("fd7a:115c:a1e0::1", _ULA),
        ("fd7a:115c:a1e0:ffff::1", _ULA),
    ],
)
def test_address_inside_allowed_cidr_accepted(address, cidr):
    assert validate_bind_address(address, cidr) == address


def test_config_refuses_unset_address():
    env = _env()
    del env["COLOPHON_BIND_ADDRESS"]
    with pytest.raises(ConfigError, match="COLOPHON_BIND_ADDRESS"):
        load_config(env)


def test_config_refuses_missing_cidr():
    env = _env()
    del env["COLOPHON_BIND_ALLOWED_CIDR"]
    with pytest.raises(ConfigError, match="COLOPHON_BIND_ALLOWED_CIDR"):
        load_config(env)


def test_config_refuses_public_address_inside_cidr():
    with pytest.raises(ConfigError, match="global"):
        load_config(
            _env(
                COLOPHON_BIND_ADDRESS="192.88.99.1",
                COLOPHON_BIND_ALLOWED_CIDR="192.88.99.0/24",
            )
        )


def test_config_refuses_address_outside_cidr():
    with pytest.raises(ConfigError, match="cidr"):
        load_config(
            _env(
                COLOPHON_BIND_ADDRESS="100.64.0.1",
                COLOPHON_BIND_ALLOWED_CIDR="192.0.2.0/24",
            )
        )


def test_config_refuses_lan_inside_overbroad_cidr():
    with pytest.raises(ConfigError, match="lan"):
        load_config(
            _env(
                COLOPHON_BIND_ADDRESS="10.1.2.3",
                COLOPHON_BIND_ALLOWED_CIDR="0.0.0.0/0",
            )
        )


def test_config_accepts_cgnat_example():
    config = load_config(_env())
    assert config.bind_address == "100.64.0.1"
    assert config.allowed_cidr == _CGNAT
    assert config.rlimit_as_bytes == 2147483648


def test_config_reads_rlimit_as_bytes():
    config = load_config(_env(COLOPHON_RLIMIT_AS_BYTES="3221225472"))
    assert config.rlimit_as_bytes == 3221225472


def test_config_refuses_bad_rlimit_as_bytes():
    with pytest.raises(ConfigError, match="COLOPHON_RLIMIT_AS_BYTES"):
        load_config(_env(COLOPHON_RLIMIT_AS_BYTES="2GiB"))
    with pytest.raises(ConfigError, match="COLOPHON_RLIMIT_AS_BYTES"):
        load_config(_env(COLOPHON_RLIMIT_AS_BYTES="0"))


def test_config_refuses_unspecified_and_lan():
    with pytest.raises(ConfigError, match="unspecified"):
        load_config(_env(COLOPHON_BIND_ADDRESS="0.0.0.0"))
    with pytest.raises(ConfigError, match="lan"):
        load_config(
            _env(
                COLOPHON_BIND_ADDRESS="192.168.0.20",
                COLOPHON_BIND_ALLOWED_CIDR="0.0.0.0/0",
            )
        )


def test_config_refuses_docker_runtime():
    with pytest.raises(ConfigError, match="podman"):
        load_config(_env(COLOPHON_PODMAN="docker"))


def test_config_refuses_blank_token():
    with pytest.raises(ConfigError, match="COLOPHON_WORKER_TOKEN"):
        load_config(_env(COLOPHON_WORKER_TOKEN=""))
