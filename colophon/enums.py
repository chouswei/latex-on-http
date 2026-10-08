# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Endleaf render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lane, output format, and input kind. Unknown values are rejected."""

from dataclasses import dataclass

from colophon.source_policy import reject_forbidden_source
from colophon.templates import TEMPLATES

LANES = ("InstruMeasure", "Weft", "Investor")
OUTPUT_FORMATS = ("pdf", "html", "docx")
INPUT_KINDS = ("markdown", "tex")

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "html": "text/html; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class JobRejected(ValueError):
    def __init__(self, reason, message=None):
        self.reason = reason
        self.message = message
        super().__init__(message or reason)


PAGE_SIZES = ("a4", "letter")


@dataclass(frozen=True)
class JobSpec:
    source: str
    input_kind: str
    output_format: str
    lane: str
    template_id: str = "document-shell"
    page_size: str = "a4"

    @property
    def content_type(self):
        return _CONTENT_TYPES[self.output_format]


# A raw preamble in the body. \documentclass keeps its own field.
_RAW_PREAMBLE = ("\\usepackage", "\\RequirePackage", "\\begin{document}")


def parse_job(payload):
    """Parse a render job. Unknown enum values raise ``JobRejected``.

    ENDLEAF-R27: the caller sends ``templateId`` and ``body``. The worker
    owns the preamble. ``input`` and ``inputKind`` are not fields.
    """
    if not isinstance(payload, dict):
        raise JobRejected("body")
    lane = payload.get("lane")
    output_format = payload.get("outputFormat")
    template_id = payload.get("templateId")
    source = payload.get("body")
    if lane not in LANES:
        raise JobRejected("lane")
    if output_format not in OUTPUT_FORMATS:
        raise JobRejected("outputFormat")
    if not isinstance(template_id, str) or template_id not in TEMPLATES:
        raise JobRejected("templateId")
    # ENDLEAF-R39-CAPS. HTML and DOCX are refused before a compile.
    if template_id == "fulldoc" and output_format != "pdf":
        raise JobRejected("outputFormat")
    if not isinstance(source, str) or source == "":
        raise JobRejected("body")
    # Absent means XeLaTeX. Any other value is a request for another engine.
    if "compiler" in payload and payload.get("compiler") != "xelatex":
        raise JobRejected("compiler")
    # Case-sensitive substring. The caller does not supply a class or a preamble.
    if "\\documentclass" in source:
        raise JobRejected("documentclass")
    reject_forbidden_source(source)
    if any(marker in source for marker in _RAW_PREAMBLE):
        raise JobRejected("preamble")
    page_size = payload.get("pageSize", "a4")
    if page_size not in PAGE_SIZES:
        raise JobRejected("pageSize", "pageSize must be a4 or letter")
    asset = TEMPLATES[template_id]
    return JobSpec(
        source=source,
        input_kind=asset.kind,
        output_format=output_format,
        lane=lane,
        template_id=template_id,
        page_size=page_size,
    )
