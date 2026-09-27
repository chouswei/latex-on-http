# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which cgroup v2 controllers a per-job sandbox may use.

The kernel list is ``/sys/fs/cgroup/cgroup.controllers``. A boot argument
such as ``cgroup_disable=memory`` removes that controller from the list.
Rootless Podman can apply a controller only when it is also delegated.
Inside a systemd user slice that delegation is
``user.slice/user-<uid>.slice/cgroup.subtree_control``. Otherwise it is
this process's own ``cgroup.controllers``.
"""

import os
from pathlib import Path

ROOT_CONTROLLERS = "/sys/fs/cgroup/cgroup.controllers"


class CpuControllerMissing(RuntimeError):
    """``--cpus`` is required. Missing ``cpu`` refuses the start."""


def parse_controllers(text):
    """Split a cgroup controller file. ``None`` means the file was unreadable."""
    if text is None:
        return None
    return frozenset(text.split())


def user_slice_subtree_path(uid=None):
    if uid is None:
        uid = os.getuid()
    return f"/sys/fs/cgroup/user.slice/user-{uid}.slice/cgroup.subtree_control"


def process_in_user_slice(cgroup_text, uid=None):
    if uid is None:
        uid = os.getuid()
    needle = f"/user.slice/user-{uid}.slice"
    return needle in (cgroup_text or "")


def resolve_available(
    *, root_text, subtree_text, own_text, process_under_user_slice=False
):
    """Return the controllers Podman may use for one job.

    A name must be in the kernel list when that file is readable. Delegation
    is the user-slice ``cgroup.subtree_control`` when this process is in that
    slice and the file can be read (an empty file means nothing is delegated).
    Otherwise delegation is this process's ``cgroup.controllers``. If no
    source can be read the set is empty, so the CPU cap fails closed.
    """
    kernel = parse_controllers(root_text)
    if process_under_user_slice and subtree_text is not None:
        delegated = parse_controllers(subtree_text)
    elif own_text is not None:
        delegated = parse_controllers(own_text)
    elif subtree_text is not None:
        delegated = parse_controllers(subtree_text)
    else:
        delegated = None
    if kernel is None and delegated is None:
        return frozenset()
    if kernel is None:
        return delegated
    if delegated is None:
        return kernel
    return kernel & delegated


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _self_cgroup():
    try:
        return Path("/proc/self/cgroup").read_text(encoding="utf-8")
    except OSError:
        return ""


def own_controllers_path(cgroup_text=None):
    text = _self_cgroup() if cgroup_text is None else cgroup_text
    relative = None
    for line in text.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[0] == "0" and parts[1] == "":
            relative = parts[2]
            break
    if not relative:
        return None
    if not relative.startswith("/"):
        relative = "/" + relative
    return "/sys/fs/cgroup" + relative + "/cgroup.controllers"


def read_host_controllers():
    """Read the live controller set. Unreadable files are skipped."""
    cgroup_text = _self_cgroup()
    uid = os.getuid()
    own_path = own_controllers_path(cgroup_text)
    return resolve_available(
        root_text=_read(ROOT_CONTROLLERS),
        subtree_text=_read(user_slice_subtree_path(uid)),
        own_text=_read(own_path) if own_path else None,
        process_under_user_slice=process_in_user_slice(cgroup_text, uid),
    )


def require_cpu_controller(controllers=None):
    """Return the controller set, or raise when ``cpu`` is absent."""
    if controllers is None:
        found = read_host_controllers()
    else:
        if isinstance(controllers, str):
            raise TypeError("controllers must be a set of names")
        found = frozenset(controllers)
    if "cpu" not in found:
        raise CpuControllerMissing(
            "cpu controller is not available; refusing to start without --cpus=1"
        )
    return found
