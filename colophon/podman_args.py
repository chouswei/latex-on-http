# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact ``podman run`` argument list for one throwaway job."""

import logging

from colophon.cgroup_caps import require_cpu_controller
from colophon.limits import (
    MEMORY_MIB,
    PIDS_LIMIT,
    SANDBOX_USER,
    TMPFS_MIB,
    WALL_SEC,
    rlimit_as_bytes,
)

logger = logging.getLogger(__name__)


def build_podman_run_args(
    *,
    podman,
    image,
    name,
    user=SANDBOX_USER,
    controllers=None,
    as_bytes=None,
):
    """Return the argv for one sandboxed job.

    The container has no network, a read-only root, one 512 MiB tmpfs, a
    non-root user, one CPU, a 256-pid cap, a 60 s wall clock, and an
    ``RLIMIT_AS`` ceiling (``--ulimit as=``, default 2048 MiB). ``--memory``
    and ``--memory-swap`` are passed only when the memory controller is
    available. Without it, Podman would fail the start or ignore the cap, so
    those flags are omitted and a warning is logged. The address-space
    ceiling stays. A missing ``cpu`` controller raises
    ``CpuControllerMissing`` and the caller must not start the container.
    ``--rm`` removes the container when the process exits. The caller still
    issues ``podman rm -f`` afterwards so a failed ``--rm`` cannot leave it.
    """
    found = require_cpu_controller(controllers)
    if as_bytes is None:
        ceiling = rlimit_as_bytes()
    else:
        ceiling = int(as_bytes)
        if ceiling <= 0:
            raise ValueError("RLIMIT_AS ceiling must be a positive number of bytes")
    memory_mode = "cgroup" if "memory" in found else "rlimit"
    if memory_mode == "rlimit":
        logger.warning(
            "cgroup memory controller is not available; omitting --memory "
            "and applying RLIMIT_AS %s bytes",
            ceiling,
        )
    args = [
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
        "--ulimit",
        f"as={ceiling}",
    ]
    if memory_mode == "cgroup":
        args.extend(
            [
                f"--memory={MEMORY_MIB}m",
                f"--memory-swap={MEMORY_MIB}m",
            ]
        )
    args.extend(
        [
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
            "--env",
            f"COLOPHON_MEMORY_MODE={memory_mode}",
            "--log-driver=none",
            "-i",
            image,
            "colophon-sandbox-render",
        ]
    )
    return args


def build_podman_kill_args(*, podman, name):
    return [podman, "kill", name]


def build_podman_rm_args(*, podman, name):
    return [podman, "rm", "-f", name]
