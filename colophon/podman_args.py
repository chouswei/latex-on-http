# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact ``podman run`` argument list for one throwaway job."""

import json
import logging
import re
import subprocess
from pathlib import Path

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

# go-units, which Podman uses to parse ``--ulimit``, leaves ``as`` disabled
# through 4.3. Podman 4.4 is the first release that accepts it. Older
# Podman gets an OCI precreate hook that writes ``RLIMIT_AS`` into the spec
# crun already understands. The hook does not replace ``/usr/bin/podman``.
ULIMIT_AS_MIN = (4, 4)
RLIMIT_ANNOTATION = "io.colophon.rlimit.as"
_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def _version_tuple(match):
    return (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))


def parse_podman_version(text):
    """Return ``(major, minor, patch)`` from ``podman version`` text or JSON."""
    raw = (text or "").strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            candidates = [data.get("Version")]
            client = data.get("Client")
            if isinstance(client, dict):
                candidates.append(client.get("Version"))
            for item in candidates:
                if isinstance(item, str):
                    found = _VERSION.search(item)
                    if found:
                        return _version_tuple(found)
    found = _VERSION.search(raw)
    if not found:
        raise ValueError("unreadable podman version")
    return _version_tuple(found)


def podman_supports_ulimit_as(version):
    """True when this Podman accepts ``--ulimit as=``."""
    return (version[0], version[1]) >= ULIMIT_AS_MIN


def probe_podman_version(podman):
    """Read the Podman version. A failed probe is treated as 4.3.

    4.3 rejects ``--ulimit as=``. Falling back to that version selects the
    precreate hook, which crun 1.8 applies, instead of a flag Podman rejects.
    """
    for argv in (
        [podman, "version", "--format", "json"],
        [podman, "--version"],
    ):
        try:
            completed = subprocess.run(
                argv,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        try:
            return parse_podman_version(completed.stdout.decode("utf-8", "replace"))
        except ValueError:
            continue
    logger.warning("podman version check failed; using the precreate RLIMIT_AS hook")
    return (4, 3, 0)


def hook_script_path():
    return (
        Path(__file__).resolve().parent
        / "share"
        / "podman-hooks"
        / "rlimit_as_precreate.py"
    )


def ensure_rlimit_hook_dir(dest=None):
    """Write the precreate hook JSON. Return the directory Podman should read.

    ``--hooks-dir`` is a Podman global flag. The JSON points at the script in
    this install. The script reads ``io.colophon.rlimit.as`` from the OCI spec
    and adds ``RLIMIT_AS`` before crun creates the container.
    """
    script = hook_script_path()
    if not script.is_file():
        raise FileNotFoundError(script)
    script.chmod(script.stat().st_mode | 0o111)
    directory = (
        Path(dest)
        if dest is not None
        else Path.home() / ".local/share/colophon/podman-hooks"
    )
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "1.0.0",
        "hook": {"path": str(script)},
        "when": {"always": True},
        "stages": ["precreate"],
    }
    (directory / "01-rlimit-as.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return directory


def build_podman_run_args(
    *,
    podman,
    image,
    name,
    user=SANDBOX_USER,
    controllers=None,
    as_bytes=None,
    podman_version=(4, 4, 0),
    hooks_dir=None,
):
    """Return the argv for one sandboxed job.

    The container has no network, a read-only root, one 512 MiB tmpfs, a
    non-root user, one CPU, a 256-pid cap, a 60 s wall clock, and an
    ``RLIMIT_AS`` ceiling (default 2048 MiB). Podman 4.4 and newer take
    ``--ulimit as=<soft>:<hard>``. Podman 4.3 does not: go-units rejects
    ``as``. That version gets ``--hooks-dir`` (a global flag, before
    ``run``) and ``--annotation io.colophon.rlimit.as=<bytes>``. The
    precreate hook writes the OCI ``RLIMIT_AS`` crun applies. ``--memory``
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
    use_ulimit = podman_supports_ulimit_as(podman_version)
    if not use_ulimit and hooks_dir is None:
        hooks_dir = ensure_rlimit_hook_dir()
    args = [podman]
    if not use_ulimit:
        args.extend(["--hooks-dir", str(hooks_dir)])
    args.extend(
        [
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
        ]
    )
    if use_ulimit:
        args.extend(["--ulimit", f"as={ceiling}:{ceiling}"])
    else:
        args.extend(["--annotation", f"{RLIMIT_ANNOTATION}={ceiling}"])
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
