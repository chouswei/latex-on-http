# pandoc-ext/diagram

Vendored from https://github.com/pandoc-ext/diagram
commit `5aaf35e6f775ddf501045fe28b03642ee73db2f4` (2025-10-27).

Licence: MIT. See LICENSE in this directory.

The Colophon image copies `diagram.lua` to `/usr/local/share/colophon/diagram.lua`.
`colophon/share/lock-diagram.lua` runs first and replaces any document
`diagram` metadata so a job cannot point the filter at another binary.
