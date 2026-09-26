# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact ``podman run`` argument list for one throwaway job."""

from colophon.limits import (
    MEMORY_MIB,
    PIDS_LIMIT,
    SANDBOX_USER,
    TMPFS_MIB,
    WALL_SEC,
)


def build_podman_run_args(*, podman, image, name, user=SANDBOX_USER):
    """Return the argv for one sandboxed job.

    The container has no network, a read-only root, one 512 MiB tmpfs, a
    non-root user, one CPU, 2048 MiB of memory, a 256-pid cap, and a 60 s
    wall clock. ``--rm`` removes it when the process exits. The caller still
    issues ``podman rm -f`` afterwards so a failed ``--rm`` cannot leave it.
    """
    return [
        podman,
        "run",
        "--rm",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--tmpfs",
        f"/tmp:rw,nosuid,nodev,size={TMPFS_MIB}m,mode=1777",
        "--user",
        user,
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
        image,
        "colophon-sandbox-render",
    ]


def build_podman_kill_args(*, podman, name):
    return [podman, "kill", name]


def build_podman_rm_args(*, podman, name):
    return [podman, "rm", "-f", name]
