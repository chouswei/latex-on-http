# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Worker limits.

``RETRY_AFTER_SEC`` (10) is sent on busy and load-shed refusals.
``INPUT_CAP_BYTES`` refuses request bodies above 16 MiB.
``COLOPHON_RLIMIT_AS_BYTES`` is the per-job ``RLIMIT_AS`` ceiling in bytes.
"""

import os

CPU_CORES = 1.0
MEMORY_MIB = 2048
# 2048 MiB. Virtual address space, not resident set size.
DEFAULT_RLIMIT_AS_BYTES = 2048 * 1024 * 1024
WALL_SEC = 60
OUTPUT_MIB = 20
OUTPUT_CAP_BYTES = OUTPUT_MIB * 1024 * 1024
TMPFS_MIB = 512
PIDS_LIMIT = 256
LOAD_AVG_1M_THRESHOLD = 3.0
MEM_AVAILABLE_MIB_THRESHOLD = 4096
HOST_LOAD_REPORT_INTERVAL_SEC = 10
REPORT_MAX_AGE_SEC = 30
RETRY_AFTER_SEC = 10
# Supervisor backstop, above the Podman --timeout, so a wall-clock kill is
# observed as Podman's timeout rather than this backstop when both are set.
SUPERVISOR_TIMEOUT_SEC = WALL_SEC + 5
# A SIGKILL at or after this elapsed time is the wall-clock cap. Earlier
# SIGKILL is the memory or pids cap.
TIMEOUT_ELAPSED_FLOOR_SEC = WALL_SEC - 1
SANDBOX_UID = 10001
SANDBOX_GID = 10001
INPUT_CAP_BYTES = 16 * 1024 * 1024
STDERR_KEEP_BYTES = 16 * 1024

SHARE_ROOT = "/usr/local/share/colophon"
SANDBOX_USER = f"{SANDBOX_UID}:{SANDBOX_GID}"

# setrlimit takes a signed rlim_t. Values above this are refused.
_RLIMIT_MAX = 2**63 - 1


class LimitError(ValueError):
    pass


def rlimit_as_bytes(environ=None):
    """Return the ``RLIMIT_AS`` ceiling in bytes.

    Unset or blank uses ``DEFAULT_RLIMIT_AS_BYTES``. Anything else that is
    not a positive integer fitting in a signed 64-bit rlimit is refused.
    """
    env = os.environ if environ is None else environ
    raw = env.get("COLOPHON_RLIMIT_AS_BYTES")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_RLIMIT_AS_BYTES
    text = str(raw).strip()
    if not text.isdigit():
        raise LimitError("COLOPHON_RLIMIT_AS_BYTES is unreadable")
    value = int(text)
    if value <= 0 or value > _RLIMIT_MAX:
        raise LimitError("COLOPHON_RLIMIT_AS_BYTES is unreadable")
    return value
