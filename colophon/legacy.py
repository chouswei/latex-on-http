# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map a legacy ``POST /builds/sync`` body onto one sandboxed job.

URL, git, tar, and cache resources are rejected: the sandbox has no network
and this fork does not fetch packages or inputs at runtime. The only compiler
is XeLaTeX, and shell-escape cannot be requested.
"""

import base64
import binascii
import json
from dataclasses import replace

from colophon.enums import INPUT_KINDS, JobRejected, parse_job


def parse_legacy_build(payload):
    if not isinstance(payload, dict):
        raise JobRejected("body")
    compiler = payload.get("compiler", "xelatex")
    if compiler != "xelatex":
        raise JobRejected("compiler")
    options = payload.get("options") or {}
    if "shell-escape" in json.dumps(options) or "shell_escape" in json.dumps(options):
        raise JobRejected("shell-escape")
    resources = payload.get("resources")
    if not isinstance(resources, list) or len(resources) != 1:
        raise JobRejected("resources")
    resource = resources[0]
    if not isinstance(resource, dict):
        raise JobRejected("resources")
    if any(key in resource for key in ("url", "git", "tar", "cache")):
        raise JobRejected("resource-fetch")
    if "content" in resource:
        source = resource["content"]
        if not isinstance(source, str):
            raise JobRejected("input")
    elif "file" in resource:
        try:
            source = base64.b64decode(resource["file"], validate=True).decode("utf-8")
        except (binascii.Error, UnicodeError) as exc:
            raise JobRejected("input") from exc
    else:
        raise JobRejected("input")
    kind = payload.get("inputKind", "tex")
    if kind not in INPUT_KINDS:
        raise JobRejected("inputKind")
    # COLOPHON-R27. Legacy content is a body. The shell template owns the
    # preamble. inputKind tex still runs XeLaTeX rather than Pandoc.
    job = parse_job(
        {
            "body": source,
            "templateId": "document-shell",
            "outputFormat": payload.get("outputFormat", "pdf"),
            "lane": payload.get("lane"),
        }
    )
    if kind == "tex":
        return replace(job, input_kind="tex")
    return job
