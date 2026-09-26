# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from colophon.cgroup_caps import (
    CpuControllerMissing,
    process_in_user_slice,
    require_cpu_controller,
    resolve_available,
)

_KERNEL = "cpuset cpu io memory hugetlb pids\n"
_KERNEL_NO_MEMORY = "cpuset cpu io hugetlb pids\n"


def test_controller_present_keeps_memory_and_cpu():
    found = resolve_available(
        root_text=_KERNEL,
        subtree_text="cpu memory pids\n",
        own_text="cpu memory pids\n",
        process_under_user_slice=True,
    )
    assert {"cpu", "memory", "pids"} <= found


def test_kernel_without_memory_drops_it():
    """``cgroup_disable=memory`` removes the controller from the kernel list."""
    found = resolve_available(
        root_text=_KERNEL_NO_MEMORY,
        subtree_text="cpu memory pids\n",
        own_text="cpu memory pids\n",
        process_under_user_slice=True,
    )
    assert "memory" not in found
    assert "cpu" in found
    assert "pids" in found


def test_user_slice_without_memory_drops_it():
    found = resolve_available(
        root_text=_KERNEL,
        subtree_text="cpu pids\n",
        own_text="cpu memory pids\n",
        process_under_user_slice=True,
    )
    assert "memory" not in found
    assert "cpu" in found


def test_empty_user_slice_fails_closed_for_cpu():
    found = resolve_available(
        root_text=_KERNEL,
        subtree_text="",
        own_text="cpu memory pids\n",
        process_under_user_slice=True,
    )
    assert "cpu" not in found


def test_outside_the_user_slice_uses_the_process_cgroup():
    found = resolve_available(
        root_text=_KERNEL,
        subtree_text="",
        own_text="cpu memory pids\n",
        process_under_user_slice=False,
    )
    assert {"cpu", "memory", "pids"} <= found


def test_missing_slice_file_falls_back_to_the_process_cgroup():
    found = resolve_available(
        root_text=_KERNEL,
        subtree_text=None,
        own_text="cpu pids\n",
        process_under_user_slice=True,
    )
    assert found == frozenset({"cpu", "pids"})


def test_unreadable_sources_are_empty():
    assert (
        resolve_available(root_text=None, subtree_text=None, own_text=None)
        == frozenset()
    )


def test_require_cpu_raises_when_absent():
    try:
        require_cpu_controller(frozenset({"memory", "pids"}))
    except CpuControllerMissing as exc:
        assert "refusing to start" in str(exc)
    else:
        raise AssertionError("cpu absence must refuse to start")


def test_process_in_user_slice_matches_the_uid_path():
    text = "0::/user.slice/user-1000.slice/user@1000.service\n"
    assert process_in_user_slice(text, uid=1000) is True
    assert process_in_user_slice(text, uid=1001) is False
    assert (
        process_in_user_slice("0::/system.slice/colophon.service\n", uid=1000) is False
    )
