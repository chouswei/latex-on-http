-- Copyright (C) 2026 Inkmirage
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Runs before pandoc-ext/diagram and replaces any document diagram metadata.
-- Callers cannot point TikZ at a shell-escape binary or turn on engines that
-- fetch tools. Mermaid and D2 are not engines in this filter. The YAML is
-- parsed by Pandoc so the types match the filter.

function Meta(meta)
  local locked = pandoc.read([[
---
diagram:
  cache: false
  engine:
    tikz:
      execpath: /usr/local/bin/xelatex-nonescape
      additional-packages: |
        \input{colophon-v1-preamble.tex}
---
]], "markdown")
  meta.diagram = locked.meta.diagram
  return meta
end
