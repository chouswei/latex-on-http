# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Host load sample and shed decision."""

import time
from datetime import datetime, timezone
from pathlib import Path

from colophon.limits import (
    HOST_LOAD_REPORT_INTERVAL_SEC,
    LOAD_AVG_1M_THRESHOLD,
    MEM_AVAILABLE_MIB_THRESHOLD,
    REPORT_MAX_AGE_SEC,
)


def read_proc_load(load_path="/proc/loadavg", meminfo_path="/proc/meminfo"):
    """Return ``(loadavg_1m, mem_available_mib)`` or raise ``OSError``."""
    load_text = Path(load_path).read_text(encoding="utf-8")
    load = float(load_text.split()[0])
    mem_kib = None
    for line in Path(meminfo_path).read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            mem_kib = int(line.split()[1])
            break
    if mem_kib is None:
        raise OSError("MemAvailable missing")
    return load, mem_kib // 1024


def shed_reason(load_avg, mem_available_mib, age_sec):
    """Return a shed reason, or ``None`` when a job may start.

    Refuse when the 1-minute load average is above 3.0, when MemAvailable
    is below 4096 MiB, or when the sample is older than 30 s. Values equal
    to the thresholds are accepted.
    """
    if age_sec is None or age_sec > REPORT_MAX_AGE_SEC:
        return "stale"
    if load_avg > LOAD_AVG_1M_THRESHOLD:
        return "loadavg"
    if mem_available_mib < MEM_AVAILABLE_MIB_THRESHOLD:
        return "mem"
    return None


class LoadMonitor:
    def __init__(self, reader=read_proc_load, clock=time.monotonic):
        self._reader = reader
        self._clock = clock
        self.load_avg = None
        self.mem_available_mib = None
        self.error = None
        self.sampled_at = None
        self.sampled_at_utc = None

    def sample(self):
        try:
            load_avg, mem_mib = self._reader()
        except Exception as exc:  # fail closed: unreadable sample sheds
            self.error = exc.__class__.__name__
            self.load_avg = None
            self.mem_available_mib = None
        else:
            self.error = None
            self.load_avg = load_avg
            self.mem_available_mib = mem_mib
        self.sampled_at = self._clock()
        self.sampled_at_utc = datetime.now(timezone.utc)

    def age_sec(self):
        if self.sampled_at is None:
            return None
        return self._clock() - self.sampled_at

    def decision(self):
        if self.error is not None or self.load_avg is None:
            return "unreadable"
        return shed_reason(self.load_avg, self.mem_available_mib, self.age_sec())

    def report(self, busy):
        reason = self.decision()
        stale = reason in ("stale", "unreadable")
        return {
            "loadAvg1m": self.load_avg,
            "memAvailableMiB": self.mem_available_mib,
            "busy": bool(busy),
            "stale": stale,
            "intervalSec": HOST_LOAD_REPORT_INTERVAL_SEC,
            "readable": reason != "unreadable",
        }

    def load_payload(self, jobs):
        """Body for ``GET /load``. The gate reads three of these fields.

        ``loadAvg1m``, ``memAvailableMiB``, and ``observedAt`` are what
        Colophon gate ``fetch_load`` requires. ``jobs`` is 0 or 1. ``queue``
        is always 0: a second job is refused, not queued. ``shed`` is the
        load-shed decision (load average, free memory against 4096 MiB, or
        a stale or unreadable sample). Occupancy is ``jobs``, not ``shed``.
        """
        reason = self.decision()
        observed = self.sampled_at_utc
        return {
            "loadAvg1m": self.load_avg,
            "memAvailableMiB": self.mem_available_mib,
            "memThresholdMiB": MEM_AVAILABLE_MIB_THRESHOLD,
            "jobs": int(jobs),
            "queue": 0,
            "shed": reason is not None,
            "shedReason": reason,
            "observedAt": None if observed is None else observed.isoformat(),
        }
