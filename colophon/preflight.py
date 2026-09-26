# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Host preflight. Fails closed. Never stops or inspects another container."""

import grp
import os
import socket
from dataclasses import dataclass

from colophon.cgroup_caps import read_host_controllers

FOREIGN_SOCKETS = (
    "/var/run/docker.sock",
    "/run/docker.sock",
    "/run/podman/podman.sock",
)
_REQUIRED_CONTROLLERS = frozenset({"cpu", "pids"})


@dataclass(frozen=True)
class PreflightProbe:
    """Facts the checker needs. Tests supply these; the CLI reads the host."""

    mounts: str
    controllers: str | None
    group_names: tuple
    accessible_sockets: tuple
    listable_sockets: tuple


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str
    warn: bool = False


def cgroup_v2_in_use(mounts):
    v2 = False
    v1 = False
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mountpoint, fstype = parts[1], parts[2]
        if fstype == "cgroup2" and mountpoint == "/sys/fs/cgroup":
            v2 = True
        if fstype == "cgroup":
            v1 = True
    return v2 and not v1


def controllers_delegated(text):
    if text is None:
        return False
    return _REQUIRED_CONTROLLERS <= set(text.split())


def evaluate(probe: PreflightProbe):
    checks = []
    v2 = cgroup_v2_in_use(probe.mounts)
    checks.append(
        Check("cgroup v2", v2, "unified hierarchy" if v2 else "not cgroup v2 only")
    )
    delegated = controllers_delegated(probe.controllers)
    checks.append(
        Check(
            "delegated controllers (cpu pids)",
            delegated,
            "present" if delegated else "missing or unreadable",
        )
    )
    if probe.controllers is None:
        memory_detail = "unreadable; rlimit mode, per-job RLIMIT_AS ceiling"
        memory_warn = True
    elif "memory" in probe.controllers.split():
        memory_detail = "present"
        memory_warn = False
    else:
        memory_detail = "absent; rlimit mode, per-job RLIMIT_AS ceiling"
        memory_warn = True
    checks.append(
        Check(
            "memory controller",
            True,
            memory_detail,
            warn=memory_warn,
        )
    )
    in_docker = "docker" in probe.group_names
    checks.append(
        Check(
            "user not in docker group",
            not in_docker,
            "docker group absent" if not in_docker else "user is in the docker group",
        )
    )
    sock_ok = len(probe.accessible_sockets) == 0
    checks.append(
        Check(
            "docker and foreign podman sockets inaccessible",
            sock_ok,
            "no access" if sock_ok else ",".join(probe.accessible_sockets),
        )
    )
    # A successful list is a failure. Connection errors are the passing case.
    cannot_list = len(probe.listable_sockets) == 0
    checks.append(
        Check(
            "cannot list other containers on the host",
            cannot_list,
            "list failed" if cannot_list else ",".join(probe.listable_sockets),
        )
    )
    return checks


def format_report(checks):
    lines = []
    for check in checks:
        if check.warn:
            state = "warn"
        elif check.passed:
            state = "pass"
        else:
            state = "fail"
        lines.append(f"{check.name}: {state} ({check.detail})")
    return "\n".join(lines) + "\n"


def report_ok(checks):
    return all(check.passed for check in checks)


def _group_names():
    gids = set(os.getgroups())
    gids.add(os.getgid())
    names = []
    for gid in gids:
        try:
            names.append(grp.getgrgid(gid).gr_name)
        except KeyError:
            continue
    return tuple(names)


def _socket_accessible(path):
    return os.path.exists(path) and os.access(path, os.R_OK)


def _list_answered(path):
    """GET the container list. Any HTTP response means the list call was served.

    This is the only foreign-runtime call. It does not stop, inspect, or
    otherwise touch a container.
    """
    if not os.path.exists(path):
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(1.0)
        sock.connect(path)
        sock.sendall(b"GET /containers/json HTTP/1.0\r\nHost: localhost\r\n\r\n")
        data = sock.recv(64)
    except OSError:
        return False
    finally:
        sock.close()
    return data.startswith(b"HTTP/")


def probe_host():
    try:
        mounts = open("/proc/mounts", encoding="utf-8").read()
    except OSError:
        mounts = ""
    accessible = tuple(path for path in FOREIGN_SOCKETS if _socket_accessible(path))
    listable = tuple(path for path in FOREIGN_SOCKETS if _list_answered(path))
    available = read_host_controllers()
    return PreflightProbe(
        mounts=mounts,
        controllers=" ".join(sorted(available)),
        group_names=_group_names(),
        accessible_sockets=accessible,
        listable_sockets=listable,
    )


def main(probe=None):
    checks = evaluate(probe if probe is not None else probe_host())
    sys_stdout = __import__("sys").stdout
    sys_stdout.write(format_report(checks))
    return 0 if report_ok(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
