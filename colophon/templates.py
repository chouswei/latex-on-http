# Copyright (C) 2017-2019 Yoan Tournade (upstream LaTeX-on-HTTP)
# Copyright (C) 2026 Inkmirage (Colophon render worker modifications)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-owned templates. COLOPHON-R27.

A caller sends ``templateId`` and a body. The worker builds the document
as that template's preamble plus the body. The class and the packages in
the preamble come from the allowlist. A caller-supplied preamble is refused
before this module runs.
"""

from dataclasses import dataclass
from pathlib import Path

from colophon.limits import SHARE_ROOT

# Gate playbook order. document-shell is Markdown. The other six are TeX.
TEMPLATE_IDS = (
    "document-shell",
    "pidcircuit",
    "circuits",
    "plots",
    "chemistry",
    "gantt",
    "floorplan",
)

# article, the base fonts, and the names in colophon-v1-preamble.tex.
# Nothing outside this set may appear in a template preamble.
ALLOWED_CLASSES = frozenset({"article"})
ALLOWED_PACKAGES = frozenset(
    {
        "fontspec",
        "xeCJK",
        "graphicx",
        "booktabs",
        "longtable",
        "hyperref",
        "tikz",
        "circuitikz",
        "siunitx",
        "pgfplots",
        "chemfig",
        "mhchem",
        "tikz-3dplot",
        "tikz-feynman",
        "tikz-cd",
        "forest",
        "tikz-timing",
        "bytefield",
        "pgfgantt",
        "tikz-dimline",
        "tikzscale",
        "colophon-floorplan",
    }
)
ALLOWED_LIBRARIES = frozenset(
    {
        "shapes",
        "arrows.meta",
        "positioning",
        "calc",
        "automata",
        "mindmap",
        "circuits.pid.ISO14617",
    }
)
ALLOWED_INPUTS = frozenset({"colophon-v1-preamble.tex"})


@dataclass(frozen=True)
class TemplateAsset:
    template_id: str
    kind: str
    example_name: str


TEMPLATES = {
    "document-shell": TemplateAsset("document-shell", "markdown", "example.md"),
    "pidcircuit": TemplateAsset("pidcircuit", "tex", "example.tex"),
    "circuits": TemplateAsset("circuits", "tex", "example.tex"),
    "plots": TemplateAsset("plots", "tex", "example.tex"),
    "chemistry": TemplateAsset("chemistry", "tex", "example.tex"),
    "gantt": TemplateAsset("gantt", "tex", "example.tex"),
    "floorplan": TemplateAsset("floorplan", "tex", "example.tex"),
}


def owned_root(root=None):
    if root is None:
        return Path(SHARE_ROOT) / "templates" / "owned"
    return Path(root)


def compose(template_id, lane, body, root=None):
    """Preamble plus body. ``root`` defaults to the image share directory."""
    path = owned_root(root) / template_id / "preamble.tex"
    text = path.read_text(encoding="utf-8")
    if text.count("__LANE__") != 1 or text.count("__BODY__") != 1:
        raise ValueError("preamble")
    return text.replace("__LANE__", lane, 1).replace("__BODY__", body, 1)


def example_body(template_id, root=None):
    asset = TEMPLATES[template_id]
    path = owned_root(root) / template_id / asset.example_name
    return path.read_text(encoding="utf-8")
