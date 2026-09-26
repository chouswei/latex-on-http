#!/usr/bin/env python3
# Copyright (C) 2026 Inkmirage
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Podman precreate hook: write RLIMIT_AS into the OCI spec.

Podman 4.3 rejects ``--ulimit as=`` because go-units leaves that name
disabled. This hook runs on the host, before crun creates the container.
stdin is the proposed OCI spec. stdout is that spec plus ``RLIMIT_AS``.
The ceiling is the annotation ``io.colophon.rlimit.as`` (bytes). A missing
or invalid annotation fails the start so the job cannot run without the cap.
"""

import json
import sys

ANNOTATION = "io.colophon.rlimit.as"


def inject(spec):
    annotations = spec.get("annotations")
    if not isinstance(annotations, dict) or ANNOTATION not in annotations:
        raise ValueError(f"missing {ANNOTATION}")
    raw = annotations[ANNOTATION]
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ValueError(f"invalid {ANNOTATION}")
    try:
        ceiling = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {ANNOTATION}") from exc
    if ceiling <= 0:
        raise ValueError(f"invalid {ANNOTATION}")
    process = spec.get("process")
    if not isinstance(process, dict):
        process = {}
        spec["process"] = process
    current = process.get("rlimits")
    if not isinstance(current, list):
        current = []
    kept = [
        item
        for item in current
        if not (isinstance(item, dict) and item.get("type") == "RLIMIT_AS")
    ]
    kept.append({"type": "RLIMIT_AS", "soft": ceiling, "hard": ceiling})
    process["rlimits"] = kept
    return spec


def main():
    try:
        spec = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("precreate hook: OCI spec is not JSON", file=sys.stderr)
        return 1
    if not isinstance(spec, dict):
        print("precreate hook: OCI spec is not an object", file=sys.stderr)
        return 1
    try:
        updated = inject(spec)
    except ValueError as exc:
        print(f"precreate hook: {exc}", file=sys.stderr)
        return 1
    json.dump(updated, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
