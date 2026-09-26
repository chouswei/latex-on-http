# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lane, output format, and input kind. Unknown values are rejected."""

from dataclasses import dataclass

from colophon.source_policy import reject_forbidden_source

LANES = ("InstruMeasure", "Weft", "Investor")
OUTPUT_FORMATS = ("pdf", "html", "docx")
INPUT_KINDS = ("markdown", "tex")

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "html": "text/html; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class JobRejected(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class JobSpec:
    source: str
    input_kind: str
    output_format: str
    lane: str

    @property
    def content_type(self):
        return _CONTENT_TYPES[self.output_format]


def parse_job(payload):
    """Parse a render job. Unknown enum values raise ``JobRejected``."""
    if not isinstance(payload, dict):
        raise JobRejected("body")
    lane = payload.get("lane")
    output_format = payload.get("outputFormat")
    input_kind = payload.get("inputKind")
    source = payload.get("input")
    if lane not in LANES:
        raise JobRejected("lane")
    if output_format not in OUTPUT_FORMATS:
        raise JobRejected("outputFormat")
    if input_kind not in INPUT_KINDS:
        raise JobRejected("inputKind")
    if not isinstance(source, str) or source == "":
        raise JobRejected("input")
    if input_kind == "tex" and "\\documentclass" in source:
        raise JobRejected("documentclass")
    reject_forbidden_source(source)
    return JobSpec(
        source=source,
        input_kind=input_kind,
        output_format=output_format,
        lane=lane,
    )
