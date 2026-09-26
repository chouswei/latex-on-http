-- Copyright (C) 2026 Inkmirage
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Runs before pandoc-ext/diagram and replaces any document diagram metadata.
-- Callers cannot point TikZ at a shell-escape binary or turn on engines that
-- fetch tools. The YAML is parsed by Pandoc so the types match the filter.

function Meta(meta)
  local locked = pandoc.read([[
---
diagram:
  cache: false
  engine:
    d2: true
    mermaid:
      execpath: /usr/local/bin/mmdc
    tikz:
      execpath: /usr/local/bin/xelatex-nonescape
      additional-packages: |
        \usepackage{fontspec}
        \usepackage{xeCJK}
        \setCJKmainfont{Noto Sans CJK TC}
        \usepackage{circuitikz}
        \usetikzlibrary{circuits.pid.ISO14617}
---
]], "markdown")
  meta.diagram = locked.meta.diagram
  return meta
end
