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
# A SIGKILL at or after this elapsed time is the wall-clock cap. An earlier
# SIGKILL is the cgroup memory or pids cap. Under RLIMIT_AS the process is
# not signalled: the allocator fails and the engine exits nonzero. That
# exit is the same memory-cap outcome. See ``allocation_failure``.
# Podman 4.3 ``run --timeout`` exits 255, not 137. Elapsed time at or after
# ``WALL_SEC`` is the timeout whatever the exit code is. An earlier 255 is not.
TIMEOUT_ELAPSED_FLOOR_SEC = WALL_SEC - 1
SANDBOX_UID = 10001
SANDBOX_GID = 10001
INPUT_CAP_BYTES = 16 * 1024 * 1024
# TikZ fences in one job. The wall-clock cap is the runaway-loop bound:
# an unbounded \loop or a huge \foreach is failTimeout at WALL_SEC, not a
# separate preflight. Gate-owned quotas (jobs per day, jobs per minute,
# a smaller input cap) are not in this list.
MAX_FENCES_PER_JOB = 5
STDERR_KEEP_BYTES = 16 * 1024

SHARE_ROOT = "/usr/local/share/colophon"
SANDBOX_USER = f"{SANDBOX_UID}:{SANDBOX_GID}"

# setrlimit takes a signed rlim_t. Values above this are refused.
_RLIMIT_MAX = 2**63 - 1


class LimitError(ValueError):
    pass


# Substrings, matched case-insensitively, from an engine that could not
# allocate. XeTeX prints "ooops, not enough memory". kpathsea prints
# "fatal: memory exhausted". xdvipdfmx prints "Out of memory - asked for
# N bytes". libc prints "Cannot allocate memory". Pandoc 3's Haskell
# runtime prints "Heap exhausted". The xdvipdfmx line "might cause out of
# memory" warns about a large bitmap and is not itself a failed allocation.
_ALLOCATION_MARKERS = (
    "not enough memory",
    "memory exhausted",
    "cannot allocate memory",
    "out of memory",
    "heap exhausted",
)
_ALLOCATION_WARNINGS = ("might cause out of memory",)


def allocation_failure(stderr):
    """Return true when ``stderr`` reports an allocation failure.

    A zero exit is not a failure. The caller decides that. Matching is
    case-insensitive so ``Out of memory`` and ``memory exhausted`` both hit.
    """
    if not stderr:
        return False
    if isinstance(stderr, bytes):
        text = stderr.decode("utf-8", "replace")
    else:
        text = str(stderr)
    folded = text.lower()
    for warning in _ALLOCATION_WARNINGS:
        folded = folded.replace(warning, "")
    return any(marker in folded for marker in _ALLOCATION_MARKERS)


def limits_payload():
    """Caps a gate can read from ``GET /version``.

    Names match the worker budget. ``maxFencesPerJob`` is the TikZ fence
    cap. Runaway TeX loops are not a separate field: they hit ``wallSec``
    and the job is ``failTimeout``.
    """
    return {
        "cpu": 1,
        "memMiB": MEMORY_MIB,
        "wallSec": WALL_SEC,
        "outputMiB": OUTPUT_MIB,
        "pidsMax": PIDS_LIMIT,
        "tmpfsMiB": TMPFS_MIB,
        "inputMiB": INPUT_CAP_BYTES // (1024 * 1024),
        "maxFencesPerJob": MAX_FENCES_PER_JOB,
        "retryAfterSec": RETRY_AFTER_SEC,
    }


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
