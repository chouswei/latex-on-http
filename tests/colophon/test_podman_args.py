# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging
import sys
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
        f"as={DEFAULT_RLIMIT_AS_BYTES}:{DEFAULT_RLIMIT_AS_BYTES}",
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
    assert f"as={DEFAULT_RLIMIT_AS_BYTES}:{DEFAULT_RLIMIT_AS_BYTES}" in args
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
    assert f"as={DEFAULT_RLIMIT_AS_BYTES}:{DEFAULT_RLIMIT_AS_BYTES}" in args
    assert "COLOPHON_MEMORY_MODE=rlimit" in args
    assert any("omitting --memory" in rec.message for rec in caplog.records)


def test_cpu_controller_absent_refuses_to_start():
    with pytest.raises(CpuControllerMissing, match="refusing to start"):
        _args(controllers=frozenset({"memory", "pids"}))


def test_rlimit_as_bytes_env_sets_the_ceiling(monkeypatch):
    monkeypatch.setenv("COLOPHON_RLIMIT_AS_BYTES", "3221225472")
    args = _args()
    assert "as=3221225472:3221225472" in args
    assert f"--memory={MEMORY_MIB}m" in args


def test_explicit_ceiling_overrides_the_env(monkeypatch):
    monkeypatch.setenv("COLOPHON_RLIMIT_AS_BYTES", "3221225472")
    args = _args(as_bytes=1073741824)
    assert "as=1073741824:1073741824" in args


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

    runner = make_podman_runner(config, KillSwitch(switch_path))
    monkeypatch.setattr(runner_mod.subprocess, "Popen", _spawn)
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


def test_podman_43_injects_rlimit_as_with_a_precreate_hook(tmp_path):
    hooks = tmp_path / "hooks"
    args = _args(podman_version=(4, 3, 1), hooks_dir=hooks)
    assert args[:4] == ["podman", "--hooks-dir", str(hooks), "run"]
    assert "--ulimit" not in args
    assert not any(str(arg).startswith("as=") for arg in args)
    assert f"io.colophon.rlimit.as={DEFAULT_RLIMIT_AS_BYTES}" in args
    assert f"--memory={MEMORY_MIB}m" in args
    assert f"--timeout={WALL_SEC}" in args
    assert "--network=none" in args


def test_podman_44_keeps_ulimit_as():
    args = _args(podman_version=(4, 4, 0))
    assert "--hooks-dir" not in args
    assert args[1] == "run"
    assert "--ulimit" in args
    assert f"as={DEFAULT_RLIMIT_AS_BYTES}:{DEFAULT_RLIMIT_AS_BYTES}" in args


def test_podman_version_selects_the_rlimit_form():
    from colophon.podman_args import parse_podman_version, podman_supports_ulimit_as

    assert parse_podman_version('{"Version":"4.3.1"}') == (4, 3, 1)
    assert parse_podman_version('{"Client":{"Version":"4.4.0"}}') == (4, 4, 0)
    assert parse_podman_version("podman version 4.3.1\n") == (4, 3, 1)
    assert podman_supports_ulimit_as((4, 3, 1)) is False
    assert podman_supports_ulimit_as((4, 4, 0)) is True
    assert podman_supports_ulimit_as((5, 0, 0)) is True


def test_probe_reads_podman_43(tmp_path):
    from colophon.podman_args import probe_podman_version

    binary = tmp_path / "podman"
    binary.write_text(
        "#!/bin/sh\nprintf '%s\\n' '{\"Version\":\"4.3.1\"}'\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    assert probe_podman_version(str(binary)) == (4, 3, 1)


def test_probe_without_podman_selects_the_hook(tmp_path):
    from colophon.podman_args import probe_podman_version

    assert probe_podman_version(str(tmp_path / "missing-podman")) == (4, 3, 0)


def test_precreate_hook_writes_rlimit_as():
    import json
    import subprocess

    from colophon.podman_args import hook_script_path

    spec = {
        "annotations": {"io.colophon.rlimit.as": "2147483648"},
        "process": {
            "args": ["colophon-sandbox-render"],
            "rlimits": [{"type": "RLIMIT_NOFILE", "soft": 1024, "hard": 1024}],
        },
    }
    completed = subprocess.run(
        [sys.executable, str(hook_script_path())],
        input=json.dumps(spec).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    body = json.loads(completed.stdout)
    by_type = {item["type"]: item for item in body["process"]["rlimits"]}
    assert by_type["RLIMIT_AS"] == {
        "type": "RLIMIT_AS",
        "soft": 2147483648,
        "hard": 2147483648,
    }
    assert by_type["RLIMIT_NOFILE"]["soft"] == 1024


def test_precreate_hook_refuses_a_spec_without_the_ceiling():
    import json
    import subprocess

    from colophon.podman_args import hook_script_path

    completed = subprocess.run(
        [sys.executable, str(hook_script_path())],
        input=b'{"process":{"args":["colophon-sandbox-render"]}}',
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode != 0
    assert b"RLIMIT_AS" not in completed.stdout


def test_hook_dir_points_at_the_precreate_script(tmp_path):
    import json

    from colophon.podman_args import ensure_rlimit_hook_dir, hook_script_path

    directory = ensure_rlimit_hook_dir(tmp_path / "hooks")
    payload = json.loads((directory / "01-rlimit-as.json").read_text(encoding="utf-8"))
    assert payload["version"] == "1.0.0"
    assert payload["stages"] == ["precreate"]
    assert payload["when"]["always"] is True
    assert payload["hook"]["path"] == str(hook_script_path())
    assert Path(payload["hook"]["path"]).is_file()


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
