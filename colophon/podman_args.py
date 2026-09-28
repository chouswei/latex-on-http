# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
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
# through 4.3. Upstream Podman 4.4 is the first release that accepts it.
# A distro build can still link a go-units without ``as``: Ubuntu 24.04's
# podman 4.9.3 rejects the flag. That binary gets the same OCI precreate
# hook as 4.3. The hook writes ``RLIMIT_AS`` into the spec crun already
# understands. The hook does not replace ``/usr/bin/podman``.
ULIMIT_AS_MIN = (4, 4)
ULIMIT_AS_REJECTED = "invalid ulimit type: as"
RLIMIT_ANNOTATION = "io.endleaf.rlimit.as"
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
    """True when this upstream version line accepts ``--ulimit as=``.

    Distro packages at or above 4.4 can still reject the flag. Call
    ``podman_accepts_ulimit_as`` before passing it.
    """
    return (version[0], version[1]) >= ULIMIT_AS_MIN


_ULIMIT_PROBE_NAME = "endleaf-ulimit-probe"


def probe_ulimit_as(podman, image):
    """Return whether this binary parses ``--ulimit as=`` for ``image``.

    Podman stores the flag as text and parses it only while creating a
    container. A command with no image never reaches that check, so the
    probe is ``podman create`` of the job image. A binary whose go-units
    leaves ``as`` disabled prints ``invalid ulimit type: as``. The probe
    container is removed either way and is not started.
    """
    if not image:
        return False
    name = _ULIMIT_PROBE_NAME
    try:
        completed = subprocess.run(
            [
                podman,
                "create",
                "--name",
                name,
                "--ulimit",
                "as=1:1",
                "--network=none",
                image,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    try:
        subprocess.run(
            [podman, "rm", "-f", name],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    if completed is None:
        return False
    text = completed.stderr.decode("utf-8", "replace") + completed.stdout.decode(
        "utf-8", "replace"
    )
    if ULIMIT_AS_REJECTED in text:
        return False
    return completed.returncode == 0


def podman_accepts_ulimit_as(podman, version, image):
    """True when this binary should receive ``--ulimit as=``."""
    if not podman_supports_ulimit_as(version):
        return False
    return probe_ulimit_as(podman, image)


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
    this install. The script reads ``io.endleaf.rlimit.as`` from the OCI spec
    and adds ``RLIMIT_AS`` before crun creates the container.
    """
    script = hook_script_path()
    if not script.is_file():
        raise FileNotFoundError(script)
    script.chmod(script.stat().st_mode | 0o111)
    directory = (
        Path(dest)
        if dest is not None
        else Path.home() / ".local/share/endleaf/podman-hooks"
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
    use_ulimit=None,
):
    """Return the argv for one sandboxed job.

    The container has no network, a read-only root, one 512 MiB tmpfs, a
    non-root user, one CPU, a 256-pid cap, a 60 s wall clock, and an
    ``RLIMIT_AS`` ceiling (default 2048 MiB). ``use_ulimit`` selects
    ``--ulimit as=<soft>:<hard>``. When it is omitted, the version line
    decides: 4.4 and newer take the flag. Podman 4.3, and a newer binary
    whose go-units rejects ``as``, get ``--hooks-dir`` (a global flag,
    before ``run``) and ``--annotation io.endleaf.rlimit.as=<bytes>``. The
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
    if use_ulimit is None:
        use_ulimit = podman_supports_ulimit_as(podman_version)
    else:
        use_ulimit = bool(use_ulimit)
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
            f"ENDLEAF_MEMORY_MODE={memory_mode}",
            "--log-driver=none",
            "-i",
            image,
            "endleaf-sandbox-render",
        ]
    )
    return args


def build_podman_kill_args(*, podman, name):
    return [podman, "kill", name]


def build_podman_rm_args(*, podman, name):
    return [podman, "rm", "-f", name]
