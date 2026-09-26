# PIDcircuitTikZ

Vendored from the MIT project jellespijker/PIDcircuitTikZ (Jelle Spijker).
The four library files carry that MIT grant in their headers.

There is no CTAN package named PIDcircuitTikZ, pidcircuit, or circuits.pid
(CTAN search on 2026-09-26). Do not substitute CircuiTikZ: that is the
separate CTAN package `circuitikz` (electrical networks), which the image
also installs from TeX Live.

The image installs these files under
`/usr/local/share/texmf/tex/latex/pidcircuittikz/` and runs `mktexlsr`.
Documents load them with `\usetikzlibrary{circuits.pid.ISO14617}`.
