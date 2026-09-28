# CHANGELOG

## 2026-09-28

* `sysml-tikz.sty` is installed in the image texmf tree. Documents load
  it with `\usepackage{sysml-tikz}`. The file is Endleaf
  `prototypes/sysml-layout/sysml-tikz.sty` at
  `7462a3188850852c47ca2c0cb5c43143ba6a0b27`. It requires only `tikz`.
  The shared preamble and the document-shell allowlist include
  `sysml-tikz`. `templateId` `sysml` is the TeX kind. `packageSetHash`
  is `73d55216488d240edccd26168576fcb402ce10794e04a3ef5ee8aec2bb166b98`.

## 2026-09-27-endleaf

* The product is Endleaf by Inkmirage (formerly Colophon). This repository
  stays `chouswei/latex-on-http`. The Python module stays `colophon`
  (`python -m colophon`). `\input{colophon-v1-preamble.tex}` is unchanged.
* `colophon-floorplan` is now `endleaf-floorplan`. `packageSetHash` is
  `f2946ed8f9682cc0e0dffa468d29fdc25ae2feb85e7d9d1291414dc1cf2a310d`
  (was `c6676798e00bd9655bf3391f0c0f21dec100684d5c6783a6e0b2c3f8ae078c01`).
  The hash changed because that one package name changed. No package was
  added or removed. `openin_any` stays `p`.
* Settings are `ENDLEAF_*`. `COLOPHON_*` is still read when the new name is
  unset, and each use logs a deprecation line.
* Floor-plan internals are `\elfloorplan@…`. LaTeX rejects a `\newcommand`
  name that starts with `\end`, so `\endleaffloorplan@` could not load.
  The package and file stay `endleaf-floorplan`, and `packageSetHash`
  stays `f2946ed8f9682cc0e0dffa468d29fdc25ae2feb85e7d9d1291414dc1cf2a310d`.

## 2026-09-26

* TeX is started on a relative name from the job directory. `openin_any`
  and `openout_any` stay `p`. The image CJK check compiles `cjk.tex` from
  `/tmp`, not `/tmp/cjk.tex`. Pandoc's absolute `input.tex` is rewritten
  to that basename by `xelatex-nonescape`. Fenced TikZ compiles
  `tikz-image.tex` in its temp directory. Owned templates are read by
  kpathsea name.
* Fork behaviour: Endleaf by Inkmirage render worker. Jobs run in throwaway rootless
  Podman sandboxes. The listener binds only to one address inside
  `ENDLEAF_BIND_ALLOWED_CIDR`, and refuses a public (`is_global`) address.
  Host-side LaTeX is disabled. See NOTICE.
* `GET /version` returns the git commit or tag baked at build time, plus
  `packageSet` and `packageSetHash` from the package list written at image
  build.
* Floor-plan TikZ styles and the listed tlmgr packages are in the image.
  Shell-escape, `\write18`, minted, TikZ `external`, Asymptote, gnuplot,
  epstopdf, the `svg` package, automatic tikz-feynman layout, and fenced
  Mermaid or D2 are refused before compilation. There is no Asymptote,
  Mermaid, D2, Chromium, or Node binary.
* `colophon-v1-preamble.tex` is the shared engine preamble for the TeX
  wrapper, the Pandoc template, and TikZ fences. Room area comes from the
  corner numbers. Dimension labels do not change under `scale=`.
* A job result carries a result class, wall time, cgroup `memory.peak` and
  `pids.peak`, and on a render error the first diagnostic. `memory.mode`
  is `cgroup` or `rlimit` when the sandbox reports it.
* Each job sets an `RLIMIT_AS` ceiling (`ENDLEAF_RLIMIT_AS_BYTES`,
  default `2147483648:2147483648`). Podman 4.4 and newer get
  `--ulimit as=<soft>:<hard>`. Podman below 4.4, including rootless 4.3.1,
  rejects that flag. The worker then passes `--hooks-dir` and annotation
  `io.endleaf.rlimit.as`, and a precreate hook writes OCI `RLIMIT_AS` for
  crun. `/usr/bin/podman` is not replaced. `--memory` and `--memory-swap` are
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
  jobs. A wall clock at or after 60 s is `failTimeout` for every exit
  code, including Podman 4.3's timeout exit 255. An earlier 255 stays a
  render error.
* `GET /v1/host-load` is the token-gated load report. JSON keys are
  `loadAvg1m`, `memAvailableMiB`, `busy`, `stale`, `intervalSec`,
  `readable`, and `reportedAt` (UTC, ISO-8601 with a `+00:00` offset).
  `busy` means a job holds the worker, not that the load average is high.
  `stale: true` is a shed. `readable: false` is HTTP 503. There is no
  `/load` path. `POST /v1/jobs/abort` kills the running container.
* Fenced TikZ diagrams load fontspec and xeCJK with Noto Sans CJK TC, the
  same fonts as the document path, so zh-TW labels in a fence are in the
  PDF image used for PDF, HTML, and DOCX. `\input`, `\include`, and
  `\openin` of an absolute path or `..` are `rejectInvalidInput` field
  `openin`. The image sets `openin_any = p` and `openout_any = p`.
  Runaway loops stay on the 60 s wall cap (`failTimeout`). More than five
  TikZ fences is field `fences`. `GET /version` publishes `limits`
  (`cpu`, `memMiB`, `wallSec`, `outputMiB`, `pidsMax`, `tmpfsMiB`,
  `inputMiB`, `maxFencesPerJob`, `retryAfterSec`). Inline siunitx and
  mhchem still return `warnings` on `X-Endleaf-Job`: objects with
  `code` `notationPdfOnly`, `packages`, and `message`. P&ID `pos` sets
  both TikZ's path time and `\flowpos`. Floor-plan lengths use the
  coordinate numbers, so a 3 m wall reads 3.00 m. Scale bar and north
  arrow are pics as well as styles. Owned examples match the playbook
  review replacements, including a Gantt chart with no `\\` after the
  last bar.
* ENDLEAF-R27. A job sends `templateId` and `body`. The worker owns
  the preamble and still refuses a caller `\documentclass` or raw
  preamble. An unknown `templateId` is `rejectInvalidInput` field
  `templateId`. The engine is XeLaTeX.
  `compiler` other than `xelatex`, and `\directlua`, are refused.
  An output over 20 MiB is `failCapHit`. The cap probe is 3000
  uncompressed pages (`dvipdfmx:config z 0`).
* Rootless storage on the Pi must be `driver=overlay` with
  `mount_program=fuse-overlayfs`. The vfs default used about 57 GB.
* Endleaf v1 renders LaTeX kinds only. Chromium, puppeteer, mermaid-cli
  (`mmdc`), d2, and their pandoc-ext/diagram engines are not in the worker.
  A Mermaid or D2 fence is `rejectInvalidInput`. Those kind fixtures are
  gone, so they no longer emit job meters. The TikZ engine stays for
  P&ID, circuits, plots, chemistry, Gantt, and floor plans.
* The required fixture set is the document shell plus P&ID, circuits,
  plots, chemistry, Gantt, and floor plans. `tikz-cd`, `forest`,
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
