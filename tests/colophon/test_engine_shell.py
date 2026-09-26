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


@pytest.mark.skipif(_LUALATEX is None, reason="lualatex is not installed")
def test_lualatex_os_execute_and_io_popen_do_not_run(tmp_path):
    side = tmp_path / "lua-side.txt"
    tex = tmp_path / "job.tex"
    side_lua = str(side).replace("\\", "/")
    # No backslash escapes inside \directlua: TeX expands them first.
    tex.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\directlua{\n"
        '  local exec = "nil"\n'
        "  if os ~= nil and os.execute ~= nil then\n"
        f'    local ok = os.execute("echo OSEXEC > {side_lua}.exec")\n'
        "    if ok == nil or ok == false then\n"
        '      exec = "refused"\n'
        "    else\n"
        '      exec = "ran"\n'
        "    end\n"
        "  end\n"
        '  local popen = "nil"\n'
        "  if io ~= nil and io.popen ~= nil then\n"
        '    local handle = io.popen("echo IOPOPEN", "r")\n'
        "    if handle == nil then\n"
        '      popen = "refused"\n'
        "    else\n"
        '      local data = handle:read("*a") or ""\n'
        "      handle:close()\n"
        '      if string.find(data, "IOPOPEN", 1, true) then\n'
        '        popen = "ran"\n'
        "      else\n"
        '        popen = "refused"\n'
        "      end\n"
        "    end\n"
        "  end\n"
        '  texio.write_nl("COLOPHON_LUA exec=" .. exec .. " popen=" .. popen)\n'
        "}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    completed = _run(
        [
            _LUALATEX,
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "job.tex",
        ],
        tmp_path,
    )
    log = (tmp_path / "job.log").read_text(encoding="utf-8", errors="replace")
    combined = completed.stdout.decode("utf-8", "replace") + log
    assert "COLOPHON_LUA exec=ran" not in combined
    assert "COLOPHON_LUA popen=ran" not in combined
    assert "COLOPHON_LUA exec=" in combined
    assert "exec=nil" in combined or "exec=refused" in combined
    assert "popen=nil" in combined or "popen=refused" in combined
    assert not Path(str(side) + ".exec").exists()
