# pandoc-ext/diagram

Vendored from https://github.com/pandoc-ext/diagram
commit `5aaf35e6f775ddf501045fe28b03642ee73db2f4` (2025-10-27).

Licence: MIT. See LICENSE in this directory.

The Colophon image copies `diagram.lua` to `/usr/local/share/colophon/diagram.lua`.
`colophon/share/lock-diagram.lua` runs first and replaces any document
`diagram` metadata so a job cannot point the filter at another binary.

Local changes:

- The TikZ template iterates `additional-packages`. A one-element list was
  not printed by `$additional-packages$`.
- `additional-packages` is read from RawBlock `.text`. `stringify` drops
  that text.
- Locked engine options overwrite fence options, so
  `opt-additional-packages` cannot replace the shared preamble. The TikZ
  compile does not pass `header-includes`.
- A failed diagram writes one `COLOPHON_DIAG` line (engine, message, fence
  index) and stops the render. The fence index is 0-based.
- The Mermaid and D2 engines are removed. Colophon v1 renders LaTeX kinds
  only. Those fences are refused before Pandoc runs.
