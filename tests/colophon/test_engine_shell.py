# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine checks that shell-escape is off.

Skipped when the engine is not installed. The image sets ``shell_escape = f``
and the XeLaTeX wrapper appends ``-no-shell-escape``. These tests pass that
flag to the local binaries so the same refusal can be checked on a Pi that
has TeX Live without building the image.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_XELATEX = shutil.which("xelatex")
_LUALATEX = shutil.which("lualatex")


def _run(argv, cwd):
    return subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        timeout=90,
        capture_output=True,
    )


@pytest.mark.skipif(_XELATEX is None, reason="xelatex is not installed")
def test_xelatex_write18_does_not_run(tmp_path):
    proof = tmp_path / "write18-proof"
    proof2 = tmp_path / "write18-proof-2"
    tex = tmp_path / "job.tex"
    tex.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        f"\\immediate\\write18{{touch {proof}}}\n"
        f"\\write18{{touch {proof2}}}\n"
        "Hello.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    _run(
        [
            _XELATEX,
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "job.tex",
        ],
        tmp_path,
    )
    assert not proof.exists()
    assert not proof2.exists()


def test_image_sets_shell_escape_off():
    dockerfile = (
        Path(__file__).resolve().parents[2] / "container" / "Dockerfile.colophon"
    ).read_text(encoding="utf-8")
    assert "shell_escape = f" in dockerfile


@pytest.mark.skipif(_LUALATEX is None, reason="lualatex is not installed")
def test_lualatex_positive_control_prints_types_then_pcall(tmp_path):
    """One job: marker, then type(), then pcall. A missing format is a refusal."""
    proof = tmp_path / "lua-exec-proof"
    tex = tmp_path / "job.tex"
    # No backslash escapes inside \directlua: TeX expands them first.
    tex.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\directlua{\n"
        '  texio.write_nl("COLOPHON_LUA_RAN")\n'
        "  local exec_fn = nil\n"
        "  if os ~= nil then exec_fn = os.execute end\n"
        "  local popen_fn = nil\n"
        "  if io ~= nil then popen_fn = io.popen end\n"
        '  texio.write_nl("COLOPHON_LUA type_execute=" .. type(exec_fn))\n'
        '  texio.write_nl("COLOPHON_LUA type_popen=" .. type(popen_fn))\n'
        f'  local ok1, r1 = pcall(exec_fn, "touch {proof}")\n'
        '  texio.write_nl("COLOPHON_LUA pcall_execute=" .. tostring(ok1) .. ":" .. tostring(r1))\n'
        '  local ok2, r2 = pcall(popen_fn, "echo IOPOPEN")\n'
        '  texio.write_nl("COLOPHON_LUA pcall_popen=" .. tostring(ok2) .. ":" .. tostring(r2))\n'
        "}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    completed = _run(
        [
            _LUALATEX,
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "job.tex",
        ],
        tmp_path,
    )
    log_path = tmp_path / "job.log"
    log = (
        log_path.read_text(encoding="utf-8", errors="replace")
        if log_path.exists()
        else ""
    )
    combined = completed.stdout.decode("utf-8", "replace") + log
    if "COLOPHON_LUA_RAN" not in combined:
        refused = "format" in combined.lower() or "not found" in combined.lower()
        assert refused, combined[-800:]
        pytest.skip("lualatex is not available: " + combined.strip().splitlines()[-1])
    ran_at = combined.find("COLOPHON_LUA_RAN")
    for needle in (
        "COLOPHON_LUA type_execute=",
        "COLOPHON_LUA type_popen=",
        "COLOPHON_LUA pcall_execute=",
        "COLOPHON_LUA pcall_popen=",
    ):
        assert combined.find(needle) > ran_at
    assert (
        "IOPOPEN"
        not in combined.split("COLOPHON_LUA pcall_popen=", 1)[-1].splitlines()[0]
    )
    assert not proof.exists()
