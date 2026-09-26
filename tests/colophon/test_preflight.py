# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

from colophon.preflight import PreflightProbe, evaluate, format_report, report_ok


def _probe(**overrides):
    base = dict(
        mounts="cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime 0 0\n",
        controllers="cpuset cpu io memory hugetlb pids\n",
        group_names=("colophon",),
        accessible_sockets=(),
        listable_sockets=(),
    )
    base.update(overrides)
    return PreflightProbe(**base)


def test_healthy_probe_passes():
    checks = evaluate(_probe())
    assert report_ok(checks)


def test_cgroup_v1_fails():
    mounts = (
        "cgroup2 /sys/fs/cgroup cgroup2 rw 0 0\n"
        "cgroup /sys/fs/cgroup/memory cgroup rw,memory 0 0\n"
    )
    checks = evaluate(_probe(mounts=mounts))
    assert report_ok(checks) is False
    assert any(check.name == "cgroup v2" and not check.passed for check in checks)


def test_missing_controllers_fail():
    checks = evaluate(_probe(controllers="cpu memory\n"))
    assert report_ok(checks) is False


def test_memory_controller_absent_warns_and_still_passes():
    checks = evaluate(_probe(controllers="cpu pids\n"))
    assert report_ok(checks) is True
    memory = [check for check in checks if check.name == "memory controller"]
    assert memory[0].warn is True
    assert memory[0].passed is True
    assert (
        "memory controller: warn (absent; rlimit mode, per-job RLIMIT_AS ceiling)"
        in format_report(checks)
    )


def test_memory_controller_present_is_not_a_warning():
    checks = evaluate(_probe())
    memory = [check for check in checks if check.name == "memory controller"]
    assert memory[0].warn is False
    assert memory[0].detail == "present"


def test_unreadable_controllers_fail():
    checks = evaluate(_probe(controllers=None))
    assert report_ok(checks) is False
    memory = [check for check in checks if check.name == "memory controller"]
    assert memory[0].warn is True
    assert "unreadable" in memory[0].detail


def test_docker_group_fails():
    checks = evaluate(_probe(group_names=("colophon", "docker")))
    assert report_ok(checks) is False


def test_accessible_docker_socket_fails():
    checks = evaluate(_probe(accessible_sockets=("/var/run/docker.sock",)))
    assert report_ok(checks) is False


def test_listing_other_containers_fails():
    checks = evaluate(_probe(listable_sockets=("/run/podman/podman.sock",)))
    assert report_ok(checks) is False
    listed = [
        check
        for check in checks
        if check.name == "cannot list other containers on the host"
    ]
    assert listed[0].passed is False
