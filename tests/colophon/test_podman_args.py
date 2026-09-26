# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

from colophon.limits import (
    MEMORY_MIB,
    PIDS_LIMIT,
    SANDBOX_UID,
    SANDBOX_USER,
    TMPFS_MIB,
    WALL_SEC,
)
from colophon.podman_args import build_podman_run_args


def test_podman_run_args_are_exact():
    args = build_podman_run_args(
        podman="podman",
        image="colophon-render:local",
        name="colophon-job-abc",
    )
    assert args == [
        "podman",
        "run",
        "--rm",
        "--name",
        "colophon-job-abc",
        "--network=none",
        "--read-only",
        "--tmpfs",
        f"/tmp:rw,nosuid,nodev,size={TMPFS_MIB}m,mode=1777",
        "--user",
        SANDBOX_USER,
        "--cpus=1",
        f"--memory={MEMORY_MIB}m",
        f"--memory-swap={MEMORY_MIB}m",
        f"--pids-limit={PIDS_LIMIT}",
        f"--timeout={WALL_SEC}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--workdir=/tmp",
        "--env",
        "HOME=/tmp",
        "--env",
        "TMPDIR=/tmp",
        "--env",
        "XDG_CACHE_HOME=/tmp/cache",
        "--env",
        "XDG_CONFIG_HOME=/tmp/config",
        "--env",
        "TEXMFVAR=/tmp/texmf-var",
        "--env",
        "TEXMFHOME=/tmp/texmf-home",
        "--env",
        "LANG=C.UTF-8",
        "--log-driver=none",
        "-i",
        "colophon-render:local",
        "colophon-sandbox-render",
    ]


def test_podman_args_do_not_open_the_host():
    args = build_podman_run_args(
        podman="podman", image="colophon-render:local", name="colophon-job-abc"
    )
    blob = " ".join(args)
    assert "--network=none" in args
    assert "docker.sock" not in blob
    assert "--privileged" not in args
    assert "--network=host" not in args
    assert "--pid=host" not in args
    assert "-v" not in args
    assert "--volume" not in args
    assert "--mount" not in args
    assert SANDBOX_USER == f"{SANDBOX_UID}:{SANDBOX_UID}"


def test_dockerfile_user_matches_podman_user():
    text = Path("container/Dockerfile.colophon").read_text(encoding="utf-8")
    assert f"--uid {SANDBOX_UID}" in text
    assert f"USER {SANDBOX_UID}:{SANDBOX_UID}" in text
