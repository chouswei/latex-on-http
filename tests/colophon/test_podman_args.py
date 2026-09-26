# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging
from pathlib import Path

import pytest

from colophon.cgroup_caps import CpuControllerMissing
from colophon.limits import (
    DEFAULT_RLIMIT_AS_BYTES,
    MEMORY_MIB,
    PIDS_LIMIT,
    SANDBOX_UID,
    SANDBOX_USER,
    TMPFS_MIB,
    WALL_SEC,
)
from colophon.podman_args import build_podman_run_args

_PRESENT = frozenset({"cpu", "memory", "pids"})
_NO_MEMORY = frozenset({"cpu", "pids"})


def _args(**overrides):
    base = dict(
        podman="podman",
        image="colophon-render:local",
        name="colophon-job-abc",
        controllers=_PRESENT,
    )
    base.update(overrides)
    return build_podman_run_args(**base)


def test_podman_run_args_are_exact():
    args = _args()
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
        "--ulimit",
        f"as={DEFAULT_RLIMIT_AS_BYTES}",
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
        "--env",
        "COLOPHON_MEMORY_MODE=cgroup",
        "--log-driver=none",
        "-i",
        "colophon-render:local",
        "colophon-sandbox-render",
    ]


def test_memory_controller_present_sets_memory_and_ulimit():
    args = _args(controllers=_PRESENT)
    assert "--cpus=1" in args
    assert f"--memory={MEMORY_MIB}m" in args
    assert f"--memory-swap={MEMORY_MIB}m" in args
    assert "--ulimit" in args
    assert f"as={DEFAULT_RLIMIT_AS_BYTES}" in args
    assert "COLOPHON_MEMORY_MODE=cgroup" in args
    assert DEFAULT_RLIMIT_AS_BYTES == 2147483648


def test_memory_controller_absent_omits_memory_and_keeps_ulimit(caplog):
    caplog.set_level(logging.WARNING)
    args = _args(controllers=_NO_MEMORY)
    assert "--cpus=1" in args
    assert f"--pids-limit={PIDS_LIMIT}" in args
    assert f"--timeout={WALL_SEC}" in args
    assert "--network=none" in args
    assert not any(arg.startswith("--memory") for arg in args)
    assert f"as={DEFAULT_RLIMIT_AS_BYTES}" in args
    assert "COLOPHON_MEMORY_MODE=rlimit" in args
    assert any("omitting --memory" in rec.message for rec in caplog.records)


def test_cpu_controller_absent_refuses_to_start():
    with pytest.raises(CpuControllerMissing, match="refusing to start"):
        _args(controllers=frozenset({"memory", "pids"}))


def test_rlimit_as_bytes_env_sets_the_ceiling(monkeypatch):
    monkeypatch.setenv("COLOPHON_RLIMIT_AS_BYTES", "3221225472")
    args = _args()
    assert "as=3221225472" in args
    assert f"--memory={MEMORY_MIB}m" in args


def test_explicit_ceiling_overrides_the_env(monkeypatch):
    monkeypatch.setenv("COLOPHON_RLIMIT_AS_BYTES", "3221225472")
    args = _args(as_bytes=1073741824)
    assert "as=1073741824" in args


def test_podman_args_do_not_open_the_host():
    args = _args()
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


def test_runner_refuses_to_start_when_cpu_is_absent(monkeypatch, config, switch_path):
    import threading

    import colophon.runner as runner_mod
    from colophon.enums import parse_job
    from colophon.killswitch import KillSwitch
    from colophon.runner import make_podman_runner

    def _missing(controllers=None):
        raise CpuControllerMissing(
            "cpu controller is not available; refusing to start without --cpus=1"
        )

    monkeypatch.setattr("colophon.podman_args.require_cpu_controller", _missing)

    def _spawn(*_args, **_kwargs):
        raise AssertionError("podman was started")

    monkeypatch.setattr(runner_mod.subprocess, "Popen", _spawn)
    runner = make_podman_runner(config, KillSwitch(switch_path))
    job = parse_job(
        {
            "input": "Hello",
            "inputKind": "markdown",
            "outputFormat": "pdf",
            "lane": "Weft",
        }
    )
    outcome = runner(job, "colophon-job-abc", threading.Event())
    assert outcome.kind == "rejectSpawnFail"
    assert outcome.detail == "cpu-controller"


def test_worker_process_refuses_to_start_without_cpu(monkeypatch, tmp_path):
    from colophon.cli import main_worker

    switch = tmp_path / "kill-switch"
    switch.write_text("clear\n", encoding="utf-8")
    monkeypatch.setenv("COLOPHON_BIND_ADDRESS", "100.64.0.1")
    monkeypatch.setenv("COLOPHON_BIND_ALLOWED_CIDR", "100.64.0.0/10")
    monkeypatch.setenv("COLOPHON_WORKER_TOKEN", "test-token-value")
    monkeypatch.setenv("COLOPHON_KILL_SWITCH_FILE", str(switch))
    monkeypatch.setenv("COLOPHON_IMAGE", "colophon-render:local")

    def _missing():
        raise CpuControllerMissing(
            "cpu controller is not available; refusing to start without --cpus=1"
        )

    monkeypatch.setattr("colophon.cli.require_cpu_controller", _missing)
    monkeypatch.setattr(
        "colophon.cli.serve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("served")),
    )
    assert main_worker() == 2
