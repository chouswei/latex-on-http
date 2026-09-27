# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Global stop-all file. Unreadable state is engaged (fail closed)."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SwitchState:
    readable: bool
    engaged: bool

    @property
    def blocks_jobs(self):
        return (not self.readable) or self.engaged


class KillSwitch:
    def __init__(self, path):
        self.path = Path(path)
        self._force_engaged = False

    def read(self):
        if self._force_engaged:
            return SwitchState(readable=False, engaged=True)
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return SwitchState(readable=False, engaged=True)
        token = text.strip()
        if token == "clear":
            return SwitchState(readable=True, engaged=False)
        if token == "engaged":
            return SwitchState(readable=True, engaged=True)
        return SwitchState(readable=False, engaged=True)

    def write(self, engaged):
        """Persist switch state. A failed write forces the engaged state."""
        payload = "engaged\n" if engaged else "clear\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=".switch-", dir=str(self.path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, self.path)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        except OSError:
            self._force_engaged = True
            raise
        self._force_engaged = False
