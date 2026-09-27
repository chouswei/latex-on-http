# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Process configuration. Unreadable or invalid config refuses startup."""

import os
from dataclasses import dataclass

from colophon.bindaddr import BindError, validate_bind_address
from colophon.limits import (
    DEFAULT_RLIMIT_AS_BYTES,
    RETRY_AFTER_SEC,
    SANDBOX_USER,
    LimitError,
    rlimit_as_bytes,
)
from colophon.settings import setting


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
    rlimit_as_bytes: int = DEFAULT_RLIMIT_AS_BYTES


def _require(env, suffix):
    value, name = setting(env, suffix)
    if value is None:
        raise ConfigError(f"ENDLEAF_{suffix} is unset")
    return value, name


def load_config(environ=None):
    env = os.environ if environ is None else environ
    bind_raw, bind_name = _require(env, "BIND_ADDRESS")
    cidr_raw, cidr_name = _require(env, "BIND_ALLOWED_CIDR")
    try:
        bind_address = validate_bind_address(bind_raw, cidr_raw)
    except BindError as exc:
        if exc.reason in {"cidr_unset", "cidr_invalid"}:
            name = cidr_name
        else:
            name = bind_name
        raise ConfigError(f"{name} refused ({exc.reason})") from exc
    token, token_name = _require(env, "WORKER_TOKEN")
    if any(ch.isspace() for ch in token):
        raise ConfigError(f"{token_name} is unreadable")
    switch, _switch_name = _require(env, "KILL_SWITCH_FILE")
    image, image_name = _require(env, "IMAGE")
    if "\n" in image or image.startswith("-"):
        raise ConfigError(f"{image_name} is unreadable")
    podman, podman_name = setting(env, "PODMAN", default="podman")
    if os.path.basename(podman) == "docker":
        raise ConfigError(f"{podman_name} must be podman, not docker")
    port_text, port_name = setting(env, "PORT", default="8080")
    retry_text, retry_name = setting(
        env, "RETRY_AFTER_SEC", default=str(RETRY_AFTER_SEC)
    )
    try:
        port = int(port_text)
        retry_after = int(retry_text)
    except ValueError as exc:
        raise ConfigError("port or retry-after is unreadable") from exc
    if not (0 < port < 65536):
        raise ConfigError(f"{port_name} is unreadable")
    if retry_after <= 0:
        raise ConfigError(f"{retry_name} is unreadable")
    try:
        as_bytes = rlimit_as_bytes(env)
    except LimitError as exc:
        raise ConfigError(str(exc)) from exc
    return WorkerConfig(
        bind_address=bind_address,
        allowed_cidr=cidr_raw,
        port=port,
        worker_token=token,
        kill_switch_file=switch,
        image=image,
        podman=podman,
        retry_after_sec=retry_after,
        rlimit_as_bytes=as_bytes,
    )
