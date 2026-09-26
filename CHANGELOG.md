# CHANGELOG

## 2026-09-26-colophon

* Fork behaviour: Colophon render worker. Jobs run in throwaway rootless
  Podman sandboxes. The listener binds only to one address inside
  `COLOPHON_BIND_ALLOWED_CIDR`, and refuses a public (`is_global`) address.
  Host-side LaTeX is disabled. See NOTICE.
* `GET /version` returns the git commit or tag baked at build time, plus
  `packageSet` and `packageSetHash` from the package list written at image
  build.
* Floor-plan TikZ styles and the listed tlmgr packages are in the image.
  Shell-escape, `\write18`, minted, TikZ `external`, Asymptote, gnuplot,
  epstopdf, the `svg` package, and automatic tikz-feynman layout are
  refused before compilation. There is no Asymptote binary.
* `colophon-v1-preamble.tex` is the shared engine preamble for the TeX
  wrapper, the Pandoc template, and TikZ fences. Room area comes from the
  corner numbers. Dimension labels do not change under `scale=`.
* A job result carries a result class, wall time, cgroup `memory.peak` and
  `pids.peak`, and on a render error the first diagnostic. `memory.mode`
  is `cgroup` or `rlimit` when the sandbox reports it.
* Each job sets `--ulimit as=<soft>:<hard>` (`COLOPHON_RLIMIT_AS_BYTES`,
  default `2147483648:2147483648`). `--memory` and `--memory-swap` are
  passed only when the memory controller is present. Preflight requires
  `cpu` and `pids`; a missing memory controller is a warning and the job
  uses rlimit mode. A missing `cpu` controller refuses startup. An
  allocation failure (`not enough memory`, `memory exhausted`,
  `Cannot allocate memory`, xdvipdfmx `Out of memory`, Pandoc
  `Heap exhausted`) is `failCapHit`, the same outcome as an early SIGKILL.
  `RLIMIT_AS` is per process, so the worst case is 256 × 2 GiB; one job
  at a time, few TeX processes, and the MemAvailable shed bound it.
  Other caps are unchanged (60 s, 20 MiB output, 256 pids, 512 MiB tmpfs,
  no network, shell-escape off, load shed at loadavg 3 or MemAvailable
  4096 MiB). The default ceiling fits the measured XeLaTeX and LuaLaTeX
  jobs. It does not fit current headless Chromium; see the README.
* The required fixture set is the document shell plus Mermaid, D2, P&ID,
  circuits, plots, chemistry, Gantt, and floor plans. `tikz-cd`, `forest`,
  `automata`, `mindmap`, `tikz-3dplot`, `tikz-feynman`, `tikz-timing`, and
  `bytefield` stay installed with a smoke compile and are not a sold kind.
* HTML and DOCX render fenced diagrams as images. Inline `siunitx` and
  `mhchem` stay PDF-only: those formats keep the source text and return
  a `notationPdfOnly` warning. The result class stays `ok`.
* Image: Debian `texlive-lang-cjk` provides `xeCJK.sty`. Pandoc PDF uses the
  `xelatex` engine name (the no-shell-escape wrapper is first on `PATH`).
  HTML responses embed diagram resources. SVG diagrams in PDF go through
  `rsvg-convert`.

## 2026-04-10-3

* Add CHANGELOG link

## 2026-04-10-2

* Option `options.compiler.force` as default to match old behavior

## 2026-04-10-1

* Add `options.compiler.force` to try to fore compilation (Latexmk `-f` option)
and always return the generated PDF
* Remove `options.bibliography.command`, as Latexmk select automatically either `bibtex` or `biber`
* Add `options.compiler.bibliography` to enable or disable automatic Latexmk bibliography compilation step (default to true)
* Add `commands` property on error output when `options.response.commands` is enabled, which detail of each command runned and its outputs

## 2026-03-17-1

* TeXLive 2026 base image

## 2025-09-23-3

* Bump Python dependencies

## 2025-09-23-2

* Kill all children processes on timeout
* Do not return partial PDF on timeout
* Add option `options.compiler.halt_on_error`
* Add option `options.compiler.silent`

## 2025-09-23-1

* Fix timeout for compilation, with proper error return
* Return compilation log files on failure (default true with option `options.response.log_files_on_failure`)

## 2025-08-06-1

* Switch to TexLive 2025
* Use `latexmk` as default runner instead of `latexrun`
* Add PostgreSQL database in prevision of job status

## 2025-02-13-1

* Fix build with XelaTeX [#43](https://github.com/YtoTech/latex-on-http/issues/43)

## 2024-06-28-2

* Run all commands in same directory to simplify path resolution for `filecontents` and uploaded resources

## 2024-06-28-1

* Set `cwd` for latexrun.py so the `filecontents` directives can work as expected #42

## 2023-06-12-1

* Timeout long LaTeX compilations and prevent zombie processes (the timeout is of 100 seconds for now)

## 2022-12-07-1

* Add clearer input spec (payload) validation

## 2022-08-03-1

* Add ghostscript runtime to the base Docker image

## 2022-07-31-1

* Make sync cache socket more reliable with lazy pirate pattern (prevent dead-lock on server crash)

## 2022-07-30-4

* Fix missing import on `app_cache.py`

## 2022-07-30-1

* Fix caching API

## 2022-05-23-1

* Fix Sentry Flask integration import

## 2022-05-17-3

* Add an environment variable `SENTRY_DSN` for Sentry tracking

## 2022-05-17-2

* Forget Alpine as Context seems [not to run](https://mailman.ntg.nl/pipermail/ntg-context/2021/101979.html) on it, keep to Debian

## 2022-05-17-1

* Use Alpine as default base image

## 2022-05-16-2

* Fix some Hy implementations after `1.0a4` bump 

## 2022-05-16-1

* Update Hy to `1.0a4`, as a consequence LaTeX-on-HTTP now require Python 3.7+
