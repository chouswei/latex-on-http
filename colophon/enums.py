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


# ENDLEAF-R56-SIZES. a4 is the default. orientation is optional; omitted
# keeps the template's own choice (sysml endleaf-fit may still turn a wide
# canvas landscape).
PAGE_SIZES = ("a4", "letter", "a3")
ORIENTATIONS = ("portrait", "landscape")


@dataclass(frozen=True)
class JobSpec:
    source: str
    input_kind: str
    output_format: str
    lane: str
    template_id: str = "document-shell"
    page_size: str = "a4"
    orientation: str | None = None
    # ENDLEAF-R66-SIZE. stocklabel only: (widthMm, heightMm, marginXMm, marginYMm).
    label_size: tuple[float, float, float, float] | None = None

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
        raise JobRejected("pageSize", "pageSize must be a4, letter or a3")
    orientation = payload.get("orientation")
    if orientation is not None and orientation not in ORIENTATIONS:
        raise JobRejected("orientation", "orientation must be portrait or landscape")
    label_size = None
    if template_id == "stocklabel":
        # ENDLEAF-R66-SIZE. A label page, not a sheet: labelSize, never pageSize.
        if output_format != "pdf":
            raise JobRejected("outputFormat", "stocklabel is pdf only")
        if "orientation" in payload or ("pageSize" in payload and payload.get("pageSize") is not None):
            raise JobRejected("pageSize", "stocklabel takes labelSize, not pageSize or orientation")
        label_size = parse_label_size(payload.get("labelSize"))
        page_size = "a4"
    elif "labelSize" in payload:
        raise JobRejected("labelSize", "labelSize is for templateId stocklabel")
    asset = TEMPLATES[template_id]
    return JobSpec(
        source=source,
        input_kind=asset.kind,
        output_format=output_format,
        lane=lane,
        template_id=template_id,
        page_size=page_size,
        orientation=orientation,
        label_size=label_size,
    )


# ENDLEAF-R66-SIZE. The gate owns the presets and the column rule; the
# worker only checks the page is sane. Millimetres.
LABEL_WIDTH_MM = (12.0, 1000.0)
LABEL_HEIGHT_MM = (9.0, 210.0)
LABEL_MARGIN_MM = (0.0, 10.0)
_LABEL_KEYS = ("widthMm", "heightMm", "marginXMm", "marginYMm")


def parse_label_size(raw):
    """``(w, h, mx, my)`` in mm from a labelSize object. ``JobRejected`` if bad."""
    if not isinstance(raw, dict) or set(raw) != set(_LABEL_KEYS):
        raise JobRejected("labelSize", "labelSize is widthMm, heightMm, marginXMm, marginYMm")
    values = []
    for key in _LABEL_KEYS:
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise JobRejected("labelSize", f"{key} must be a number")
        values.append(round(float(value), 2))
    width, height, mx, my = values
    if not (LABEL_WIDTH_MM[0] <= width <= LABEL_WIDTH_MM[1] and LABEL_HEIGHT_MM[0] <= height <= LABEL_HEIGHT_MM[1]):
        raise JobRejected("labelSize", "label page out of range")
    if not all(LABEL_MARGIN_MM[0] <= m <= LABEL_MARGIN_MM[1] for m in (mx, my)) or 2 * mx >= width or 2 * my >= height:
        raise JobRejected("labelSize", "label margins out of range")
    return (width, height, mx, my)


def job_payload(job):
    """ENDLEAF-R56-WIRE. The sandbox stdin for ``job``.

    ``parse_job(job_payload(job)) == job`` for every job ``parse_job``
    returns. The runner must send this, never a hand-built dict, so a
    new JobSpec field cannot be dropped between the HTTP worker and the
    sandbox again.
    """
    payload = {
        "body": job.source,
        "templateId": job.template_id,
        "outputFormat": job.output_format,
        "lane": job.lane,
        "pageSize": job.page_size,
    }
    if job.orientation is not None:
        payload["orientation"] = job.orientation
    if job.label_size is not None:
        del payload["pageSize"]
        payload["labelSize"] = dict(zip(_LABEL_KEYS, job.label_size))
    return payload
