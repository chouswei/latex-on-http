# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Process configuration. Unreadable or invalid config refuses startup."""

import os
from dataclasses import dataclass

from colophon.bindaddr import BindError, validate_bind_address
from colophon.limits import RETRY_AFTER_SEC, SANDBOX_USER


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerConfig:
    bind_address: str
    allowed_cidr: str
    port: int
    worker_token: str
    kill_switch_file: str
    image: str
    podman: str
    retry_after_sec: int
    sandbox_user: str = SANDBOX_USER


def _required(environ, name):
    value = environ.get(name)
    if value is None or str(value).strip() == "":
        raise ConfigError(f"{name} is unset")
    return str(value).strip()


def load_config(environ=None):
    env = os.environ if environ is None else environ
    bind_raw = _required(env, "COLOPHON_BIND_ADDRESS")
    cidr_raw = _required(env, "COLOPHON_BIND_ALLOWED_CIDR")
    try:
        bind_address = validate_bind_address(bind_raw, cidr_raw)
    except BindError as exc:
        if exc.reason in {"cidr_unset", "cidr_invalid"}:
            name = "COLOPHON_BIND_ALLOWED_CIDR"
        else:
            name = "COLOPHON_BIND_ADDRESS"
        raise ConfigError(f"{name} refused ({exc.reason})") from exc
    token = _required(env, "COLOPHON_WORKER_TOKEN")
    if any(ch.isspace() for ch in token):
        raise ConfigError("COLOPHON_WORKER_TOKEN is unreadable")
    switch = _required(env, "COLOPHON_KILL_SWITCH_FILE")
    image = _required(env, "COLOPHON_IMAGE")
    if "\n" in image or image.startswith("-"):
        raise ConfigError("COLOPHON_IMAGE is unreadable")
    podman = env.get("COLOPHON_PODMAN", "podman").strip() or "podman"
    if os.path.basename(podman) == "docker":
        raise ConfigError("COLOPHON_PODMAN must be podman, not docker")
    port_text = env.get("COLOPHON_PORT", "8080").strip()
    retry_text = env.get("COLOPHON_RETRY_AFTER_SEC", str(RETRY_AFTER_SEC)).strip()
    try:
        port = int(port_text)
        retry_after = int(retry_text)
    except ValueError as exc:
        raise ConfigError("port or retry-after is unreadable") from exc
    if not (0 < port < 65536):
        raise ConfigError("COLOPHON_PORT is unreadable")
    if retry_after <= 0:
        raise ConfigError("COLOPHON_RETRY_AFTER_SEC is unreadable")
    return WorkerConfig(
        bind_address=bind_address,
        allowed_cidr=cidr_raw,
        port=port,
        worker_token=token,
        kill_switch_file=switch,
        image=image,
        podman=podman,
        retry_after_sec=retry_after,
    )
