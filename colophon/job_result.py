# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-job result class and cgroup meters for the gate."""


def result_class(kind):
    """Map an internal kind to ok, failTimeout, failCapHit, renderError, or refused."""
    if kind == "ok":
        return "ok"
    if kind == "failTimeout":
        return "failTimeout"
    if kind == "failCapHit":
        return "failCapHit"
    if kind == "rejectRenderError":
        return "renderError"
    return "refused"


def job_record(
    kind,
    wall_sec,
    memory_peak,
    pids_peak,
    diagnostic=None,
    warnings=None,
    memory_mode=None,
    tex_warnings=None,
):
    memory = {"peak": memory_peak}
    if memory_mode in ("cgroup", "rlimit"):
        memory["mode"] = memory_mode
    record = {
        "result": result_class(kind),
        "wallSec": wall_sec,
        "memory": memory,
        "pids": {"peak": pids_peak},
    }
    if diagnostic is not None:
        record["diagnostic"] = diagnostic
    if warnings:
        record["warnings"] = warnings
    # ENDLEAF-R57-WARN. The key is absent on a clean render.
    if tex_warnings and any(tex_warnings.values()):
        record["texWarnings"] = dict(tex_warnings)
    return record
