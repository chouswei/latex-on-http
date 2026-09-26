# LaTeX-On-HTTP

This repository is the Colophon render worker, an AGPL-3.0 fork of
YtoTech/latex-on-http. Modifications are described in [NOTICE](NOTICE). The
upstream HTTP API notes follow the Colophon section. Sandbox rules win where
they disagree with the upstream service.

## Colophon render worker

The worker turns Markdown (with TikZ) or a TeX body into PDF, HTML, or
DOCX. Fenced Mermaid and D2 are refused before compilation
(`rejectInvalidInput`, field `mermaid` or `d2`). It runs as a dedicated
rootless user beside other
containers on the host, and is reached only from the gateway. It does not
deploy itself. Isolation comes from the per-job sandbox.

### Image

Build on an arm64 host, or any machine that can produce an arm64 image.
`COLOPHON_GIT_COMMIT` is the commit or tag baked into the image label and
into `GET /version`:

```sh
podman build --platform linux/arm64 \
  --build-arg COLOPHON_GIT_COMMIT="$(git rev-parse HEAD)" \
  -f container/Dockerfile.colophon -t colophon-render:local .
```

The image is multi-arch (`linux/arm64` and `linux/amd64`). It bakes a trimmed
TeX Live, Pandoc 3.6.4, and pandoc-ext/diagram with the TikZ engine only.
Chromium, Node, mermaid-cli, and d2 are not installed. Package managers are
not used at runtime. PIDcircuitTikZ is vendored because it is not a CTAN
package; CircuiTikZ is the CTAN package `circuitikz`.
`colophon-floorplan.sty` adds the floor-plan TikZ styles. See [NOTICE](NOTICE).

GitHub Actions workflow `arm64 CI, not Pi proof` builds the arm64 image on
`ubuntu-24.04-arm` and runs the LaTeX fixture suite under the same caps.
That run is not a Raspberry Pi proof.

Engine packages are loaded from `colophon-v1-preamble.tex`, which the TeX
wrapper, the Pandoc template, and TikZ diagram blocks all input. A fence
option cannot replace that list. `packages-once.tex` only checks that the
packages are installed.

The required fixture set is the document shell plus P&ID, circuits, plots
(a small 3D sample), chemistry, Gantt, and floor plans. Mermaid and D2
have no fixtures and do not report job meters.
`tikz-cd`, `forest`, `automata`, `mindmap`, `tikz-3dplot`, `tikz-feynman`,
`tikz-timing`, and `bytefield` stay installed and have a smoke compile.
They are not a sold kind. The tikz-feynman refusal stays.

Fenced diagrams in HTML and DOCX are images. Inline `siunitx` and `mhchem`
notation is typeset in PDF only. For HTML and DOCX the worker keeps that
notation as source text and adds a `notationPdfOnly` warning to
`X-Colophon-Job`. The result class stays `ok`.

### Dedicated rootless user

Create a user that is not in the `docker` group and has no access to
`/var/run/docker.sock` or the rootful Podman socket. Enable lingering so the
user manager stays up, and delegate the cgroup v2 `cpu` and `pids`
controllers to that user (systemd user delegation, or the equivalent
`cgroup.subtree_control` on the user slice). Delegate `memory` as well when
the kernel has that controller. A boot with `cgroup_disable=memory` has no
memory controller; the worker still installs, and each job uses the
address-space ceiling below instead of `--memory`.

```sh
sudo useradd --create-home --shell /bin/bash colophon
sudo loginctl enable-linger colophon
# Confirm the user is not in the docker group:
id colophon
```

As that user, install rootless Podman and `fuse-overlayfs`, then this repo,
and build the image above. Do not mount the Docker socket into the user
session.

Rootless Podman picks the `vfs` storage driver when `fuse-overlayfs` is
absent. On the Pi that store used about 57 GB. Pin `overlay` with
`fuse-overlayfs` before the first pull or build. A store already created
as `vfs` is not converted by this file; remove
`~/.local/share/containers/storage` only when the images in it can be
rebuilt, then build again.

```sh
sudo apt-get install -y podman fuse-overlayfs
sudo -u colophon -H bash -lc 'mkdir -p ~/.config/containers && cat > ~/.config/containers/storage.conf <<EOF
[storage]
driver = "overlay"

[storage.options]
mount_program = "/usr/bin/fuse-overlayfs"
EOF'
```

`mount_program` is the `fuse-overlayfs` binary (`command -v fuse-overlayfs`
when it is not `/usr/bin/fuse-overlayfs`).

```sh
sudo -u colophon -H bash -lc 'cd /opt/colophon && uv sync'
```

Preflight (non-zero if any required check fails; it does not stop or inspect
other containers on the host beyond a list attempt on foreign sockets). A
missing memory controller is a warning, not a failure. A missing `cpu` or
`pids` controller fails closed:

```sh
sudo -u colophon -H bash -lc 'cd /opt/colophon && uv run python -m colophon.preflight'
```

### Configuration

The process refuses to start unless every required variable is set.
`COLOPHON_BIND_ADDRESS` is the single address the gateway uses to reach this
process. Replace the placeholder `WORKER_BIND_ADDR`. It must fall inside
`COLOPHON_BIND_ALLOWED_CIDR`. An unset address, an unset or invalid CIDR,
`0.0.0.0`, `::`, a hostname, loopback, link-local, multicast, an RFC1918
LAN address, and any address Python's `ipaddress` marks `is_global` are
refused, even when the CIDR is wide enough to include them. A unique-local
address is allowed only inside that CIDR.

Common overlay examples are Tailscale's `100.64.0.0/10` and
`fd7a:115c:a1e0::/48`. The address below is an example inside the first
range, not a deployed host.

```sh
# /home/colophon/.config/colophon/worker.env  (mode 0600)
COLOPHON_BIND_ADDRESS=100.64.0.1
COLOPHON_BIND_ALLOWED_CIDR=100.64.0.0/10
COLOPHON_WORKER_TOKEN=WORKER_TOKEN
COLOPHON_KILL_SWITCH_FILE=/home/colophon/.config/colophon/kill-switch
COLOPHON_IMAGE=colophon-render:local
COLOPHON_PORT=8080
COLOPHON_GIT_COMMIT=unknown
# Optional. Per-job RLIMIT_AS ceiling in bytes. Default 2147483648 (2048 MiB).
# COLOPHON_RLIMIT_AS_BYTES=2147483648
```

Set `COLOPHON_GIT_COMMIT` to the same commit or tag passed to the image
build. `GET /version` returns that value and a link to this repository.

`printf 'clear\n' > /home/colophon/.config/colophon/kill-switch`

An unreadable or unrecognised kill-switch file is treated as engaged. The
token is the shared worker token from the gateway, sent as
`Authorization: Bearer`. It is not an end-user API key.

`Retry-After` defaults to 10 seconds. Request bodies above 16 MiB are
refused.

### Per-job caps

Every job is one rootless container: no network, read-only root, 512 MiB
tmpfs, uid 10001, `--pids-limit=256`, `--timeout=60`, shell-escape off, and
`--cpus=1`. Output over 20 MiB is `failCapHit`. A second job is refused.
Load above 3.0, or MemAvailable below 4096 MiB, sheds the job.

The memory ceiling is always an `RLIMIT_AS` of soft and hard equal to the
same value. The default is `2147483648:2147483648` (2048 MiB), from
`COLOPHON_RLIMIT_AS_BYTES`. That limit is virtual address space, not
resident set size.

Podman 4.4 and newer receive `--ulimit as=<soft>:<hard>`. Podman 4.3
(the Pi's rootless 4.3.1) rejects that flag: its go-units build leaves
`as` disabled. The worker reads `podman version` and, below 4.4, does not
pass `--ulimit as=` and does not replace `/usr/bin/podman`. It passes the
global flag `--hooks-dir` and `--annotation io.colophon.rlimit.as=<bytes>`.
A Colophon precreate hook reads that annotation and writes
`process.rlimits` entry `RLIMIT_AS` into the OCI spec. crun 1.8 applies
that rlimit when it creates the container. A missing annotation fails the
hook, so the job does not start without the cap. A failed version probe
uses this hook path.

`--memory=2048m` and `--memory-swap=2048m` are added only when the memory
controller is available. The worker reads `/sys/fs/cgroup/cgroup.controllers`
and, when the process is in the user slice, that slice's
`cgroup.subtree_control`. If `memory` is missing (including
`cgroup_disable=memory`), those two flags are omitted and the process logs
a warning. Podman then cannot fail the start, or silently drop the cap,
because of `--memory`. The address-space ceiling remains. If `cpu` is
missing, the worker refuses to start and a job launch does not run Podman.

`X-Colophon-Job` carries `memory.mode` when the sandbox reports it:
`cgroup` when `--memory` was applied, `rlimit` when the ceiling is only
`RLIMIT_AS`. Without the memory controller, `memory.peak` stays null; there
is no cgroup peak counter. `RLIMIT_AS` does not report a peak.

`RLIMIT_AS` counts virtual address space, including reservations the
process never touches. It is not resident set size.

Checked on this host with TeX Live 2023 (the image is Debian bookworm TeX
Live, so the binaries are not identical). Under a ceiling of 2147483648
bytes, all of these exited 0:

| Job | VmPeak |
| --- | --- |
| XeLaTeX, shared preamble, siunitx, mhchem, chemfig, 3D pgfplots `samples=2` | 333 MiB |
| XeLaTeX, `fontspec`, Noto Sans CJK TC | 471 MiB |
| LuaLaTeX, `fontspec`, Noto Sans CJK TC, a small pgfplots plot, first run | 1046 MiB |
| That LuaLaTeX job again, font cache already built | 578 MiB |

The default therefore does not break those TeX jobs. A LuaTeX run that
reserves more than 2048 MiB of address space, for example a large
`luaotfload` cache, fails the allocation even when the resident set would
have fitted. This worker compiles with XeLaTeX. LuaTeX is not the job engine.

Under the cgroup memory controller, a memory hit is an early SIGKILL and
the result is `failCapHit`. Under `RLIMIT_AS` the process is not signalled.
The engine exits nonzero and the log carries an allocation failure.
XeTeX prints `ooops, not enough memory`. kpathsea prints
`fatal: memory exhausted`. xdvipdfmx prints
`Out of memory - asked for N bytes`. libc prints `Cannot allocate memory`.
Pandoc 3 is not installed on the host used for that check; its Haskell
runtime prints `Heap exhausted`. Those exits are `failCapHit`, the same
outcome as the early SIGKILL. A normal TeX error is still `renderError`.

A run whose wall clock is at least 60 s is `failTimeout`, whatever the
exit code. Podman 4.3 `run --timeout` exits 255 when it kills the job
(measured at 60.9 s for an infinite `\loop`). Exit 255 before 60 s is a
different Podman error and stays `renderError`. A SIGKILL (137 or -9) at
the timeout is the same `failTimeout`.

`RLIMIT_AS` applies per process, not per container. With `--pids-limit=256`
and a 2048 MiB ceiling, the worst-case total is 256 × 2 GiB. In practice
the total stays far below that. A TeX job spawns few processes, the worker
runs one job at a time, and a new job is refused when MemAvailable is
below 4096 MiB.

Start (one process; threads serve abort and load while a job runs):

```sh
sudo -u colophon -H bash -lc 'set -a; . ~/.config/colophon/worker.env; set +a; cd /opt/colophon && uv run python -m colophon'
```

### HTTP

Canonical paths: `POST /v1/jobs`, `GET /v1/host-load`, `POST /v1/switch`,
`POST /builds/sync`, `GET /version`. `POST /v1/jobs/abort` kills the running
container. There is no `/load` path.

Every token-gated route answers `401` with `{"error":"unauthorized"}` when
the bearer token is missing or wrong. `Cache-Control` is `no-store`.

| Method and path | Role |
| --- | --- |
| `POST /v1/jobs` | Render one job. Body: `input`, `inputKind` (`markdown` or `tex`), `outputFormat` (`pdf`, `html`, `docx`), `lane` (`InstruMeasure`, `Weft`, `Investor`). Unknown values are rejected. |
| `POST /builds/sync` | Upstream-shaped body with one inline resource. `compiler` must be `xelatex`. URL fetches are rejected. `lane` is required. Success and error bodies match `POST /v1/jobs`. |
| `POST /v1/jobs/abort` | Kills the running container only. `200` `{"aborted":true}`. Idle is `404` `{"aborted":false,"error":"idle"}`. |
| `GET /v1/host-load` | Host sample, refreshed every 10 s. `200` when the sample was read, including a sample older than 30 s. `503` when the sample could not be read. |
| `POST /v1/switch` | `{"engaged": true}` or `false`. A failed write fails closed. Success JSON is `readable` and `engaged`. |
| `GET /version` | `version`, `commit`, `source`, `packageSet` (sorted TeX package names, including `colophon-floorplan`), and `packageSetHash` (sha256 of those names joined by newlines, no trailing newline). The list is written at image build. The request does not run a shell. |

`GET /v1/host-load` JSON keys, and no others:

| Key | JSON type | Meaning |
| --- | --- | --- |
| `loadavg` | number or `null` | 1-minute load average (`/proc/loadavg` field 1). |
| `memAvailableMiB` | integer or `null` | `MemAvailable` in MiB. |
| `activeJobs` | integer | `0` or `1`. |
| `queued` | integer | Always `0`. A second job is refused, not queued. |
| `reportedAt` | string or `null` | Sample time, UTC, ISO-8601 with a numeric offset (`+00:00`). A caller treats a report older than 30 s as stale. |

On `503`, `loadavg` and `memAvailableMiB` are `null`. `reportedAt` is still
the time of that failed sample.

`POST /v1/jobs` success is HTTP `200`. The body is the artifact bytes, not
JSON. `X-Colophon-Result` is `ok`. `X-Colophon-Job` is compact JSON:

| Key | JSON type | Meaning |
| --- | --- | --- |
| `result` | string | `ok`. |
| `wallSec` | number or `null` | Runner wall clock. |
| `memory.peak` | integer or `null` | cgroup peak, when the sandbox reported one. |
| `memory.mode` | string | `cgroup` or `rlimit`, only when the sandbox reported it. |
| `pids.peak` | integer or `null` | cgroup pid peak. |
| `warnings` | array of string | Present only for `notationPdfOnly`. |

`POST /v1/jobs` errors are JSON. The object always has `error`, `result`,
`wallSec`, `memory` (`peak`, and `mode` only when reported), and `pids`
(`peak`). `result` is `ok`, `failTimeout`, `failCapHit`, `renderError`, or
`refused`. Peaks and `wallSec` are `null` when the job never started.

| `error` | HTTP | `result` | Extra keys |
| --- | --- | --- | --- |
| `rejectBusy` | 429, `Retry-After` | `refused` | none when the worker is already busy |
| `rejectLoadShed` | 429, `Retry-After` | `refused` | `reason` (`loadavg`, `mem`, `stale`, `unreadable`) and `load` (the five `GET /v1/host-load` keys; `activeJobs` is `0`) |
| `rejectKillSwitch` | 403 | `refused` | `readable`, `engaged` |
| `rejectInvalidInput` | 400 | `refused` | `field` (`lane`, `outputFormat`, `inputKind`, `input`, `documentclass`, `write18`, `mermaid`, `d2`, and the other source-policy reasons) |
| `rejectSpawnFail` | 500 | `refused` | none |
| `rejectRenderError` | 422 | `renderError` | `diagnostic` when the sandbox reported one: `engine`, `message`, `file`, `line`, `fence` |
| `failTimeout` | 408 | `failTimeout` | none |
| `failCapHit` | 413 | `failCapHit` | none. Output over 20 MiB uses this kind. The body does not contain `failOutputCap`. |

A request body over 16 MiB is `rejectInvalidInput` with `field` `input`
(HTTP 400).

`403` `rejectKillSwitch` when the switch file is missing or unreadable:

```json
{"error":"rejectKillSwitch","result":"refused","wallSec":null,"memory":{"peak":null},"pids":{"peak":null},"readable":false,"engaged":true}
```

When the file is readable and contains `engaged`, `readable` is `true` and
`engaged` is `true`. Any other contents are treated as unreadable: `readable`
is `false` and `engaged` is `true`.

A second job while one is running is `429` `rejectBusy` with `Retry-After`
and is not queued. Load average above 3.0, MemAvailable below 4096 MiB, or
a sample older than 30 s is `429` `rejectLoadShed`. A wall-clock kill is
HTTP 408 `failTimeout`. A render failure is HTTP 422 `rejectRenderError`.

### Tests

```sh
uv run pytest -vv
uv run pytest -m podman -o addopts=    # needs rootless podman; skips without the image
```

Engine checks for `\write18` and Lua `os.execute` / `io.popen` run under
pytest when `xelatex` or `lualatex` is on `PATH`, and are skipped otherwise.
`scripts/colophon-negative-tests.sh` is the live check for a running worker
(timeout, shell-escape, tmpfs, the 20 MiB output cap, and one smoke render
per package family). It needs `COLOPHON_URL` and `COLOPHON_WORKER_TOKEN`.

---

> Compiles LaTeX documents through an HTTP API.

See [TUG2020 introduction](https://www.youtube.com/watch?v=tGD4upJIUgc) to LaTeX-on-HTTP genesis.

# Live @ latex.ytotech.com

Available on https://latex.ytotech.com as an open beta.

Try the interactive demo: https://latex-http-demo.ytotech.com

# Getting started

## Hello world GET Querystring API

You can pass your LaTeX document to compile in a `content` GET parameter:

[https://latex.ytotech.com/builds/sync?content=\documentclass{article} \begin{document} Hello World LaTeX-On-HTTP \end{document}](https://latex.ytotech.com/builds/sync?content=%5Cdocumentclass%7Barticle%7D%20%5Cbegin%7Bdocument%7D%20Hello%20World%20LaTeX-On-HTTP%20%5Cend%7Bdocument%7D)

You can also pass your document by url using `url` parameter:

https://latex.ytotech.com/builds/sync?url=https://raw.githubusercontent.com/YtoTech/latex-on-http/master/examples/templates/moderncv.tex

It is possible to specify the LaTeX compiler with `compiler` parameter:

https://latex.ytotech.com/builds/sync?compiler=xelatex&url=https://raw.githubusercontent.com/YtoTech/latex-on-http/master/examples/gitlab_ci/Dossier_Eleve.tex

When you need to add annex resources (for eg. other LaTeX files or image files), you can specify them using `resource-path[]`, `resource-value[]` and `resource-type[]` parameters:


[https://latex.ytotech.com/builds/sync?content=content=\documentclass{article} \usepackage{graphicx} \begin{document} Hello World \includegraphics[height%3D2cm%2Cwidth%3D7cm%2Ckeepaspectratio%3Dtrue]{logo.png} \end{document}&resource-type[]=url&resource-path[]=logo.png&resource-value[]=https://www.ytotech.com/images/ytotech_logo.png](https://latex.ytotech.com/builds/sync?content=%5Cdocumentclass%7Barticle%7D%20%5Cusepackage%7Bgraphicx%7D%20%5Cbegin%7Bdocument%7D%20Hello%20World%20%5Cincludegraphics%5Bheight%3D2cm%2Cwidth%3D7cm%2Ckeepaspectratio%3Dtrue%5D%7Blogo.png%7D%20%5Cend%7Bdocument%7D&resource-type[]=url&resource-path[]=logo.png&resource-value[]=https://www.ytotech.com/images/ytotech_logo.png)


## Hello world POST JSON API

With Curl:

```sh
curl -v -X POST https://latex.ytotech.com/builds/sync \
    -H "Content-Type:application/json" \
    -d '{
        "compiler": "lualatex",
        "resources": [
            {
                "main": true,
                "content": "\\documentclass{article}\n \\usepackage{graphicx}\n  \\begin{document}\n Hello World\\\\\n \\includegraphics[height=2cm,width=7cm,keepaspectratio=true]{logo.png}\n \\include{page2}\n \\end{document}"
            },
            {
                "path": "logo.png",
                "url": "https://www.ytotech.com/images/ytotech_logo.png"
            },
            {
                "path": "page2.tex",
                "file": "VGhpcyBpcyB0aGUgc2Vjb25kIHBhZ2UsIHdoaWNoIHdhcyBwYXNzZWQgYXMgYSBiYXNlNjQgZW5jb2RlZCBmaWxl"
            }
        ]
    }' \
    > hello_world.pdf
```

In this example the main document is passed as a plain-string (Json-encoded `content` resource mode), the logo image file with an url (`url` resource mode)
and the second LaTeX file as a base64 encoded string (`file` resource mode, which expects the file content as base64).

Also note how the first document is flag with the `main` property and how the dependencies relative paths are specified to reconstruct the file arborescence server-side for the compilation with multiple files to work.

## Hello world Multipart API

With [HTTPie](https://github.com/jakubroztocil/httpie):

```sh
http --multipart --download --output hello.pdf -v POST https://latex.ytotech.com/builds/sync \
    compiler=pdflatex \
    resources='[{"main": true, "content": "\\documentclass{article}\n \\begin{document}\n Hello World\n \\end{document}"}]'
```

This multi-part API allows to send resource files to be compiled in a multipart HTTP query.

[See more](https://github.com/YtoTech/latex-on-http/tree/master/examples/httpie_multipart).

## Available packages and fonts

Use https://latex.ytotech.com/packages and https://latex.ytotech.com/fonts to see currently available packages and fonts.

You miss something?
Open a PR for [adding font(s)](https://github.com/YtoTech/latex-on-http/blob/master/container/tl-distrib-debian.Dockerfile#L34) or [Latex/CTAN packages](https://github.com/YtoTech/latex-on-http/blob/master/container/install_latex_packages.sh#L22)!

# Using CLI

## lol

[kpym](https://github.com/kpym) has created a CLI tool named [lol](https://github.com/kpym/lol) for using LaTeX-on-HTTP:

```sh
lol -s ytotech -c xelatex main.tex imgs/*.png
```

### Installing `lol`

To install it, download the [latest release](https://github.com/kpym/lol/releases) for your platform and add it to your PATH.

For eg. on most Linux distributions this should work (considering `$HOME/.local/bin` is in your PATH):

```sh
wget https://github.com/kpym/lol/releases/download/v0.1.3/lol_0.1.3_Linux_64bit.tar.gz
tar -xf lol_0.1.3_Linux_64bit.tar.gz
chmod +x ./lol
mv ./lol ~/.local/bin
lol -h
```

# API

This project is in an experimental phase and the API is *very likely* to change.

# Compiling LaTeX

### `POST:/builds/sync`

Compile a LaTeX document, waiting for the end of the build to get back the file.

>  Request

`POST:/builds/sync` 

Payload (json)
```json
{
    "compiler": "lualatex",
    "resources": [
        {
            "main": true,
            "content": "\\documentclass{article}\n \\usepackage{graphicx}\n  \\begin{document}\n Hello World\\\\\n \\includegraphics[height=2cm,width=7cm,keepaspectratio=true]{logo.png}\n \\include{page2}\n \\end{document}"
        },
        {
            "path": "logo.png",
            "url": "https://www.ytotech.com/images/ytotech_logo.png"
        },
        {
            "path": "page2.tex",
            "file": "VGhpcyBpcyB0aGUgc2Vjb25kIHBhZ2UsIHdoaWNoIHdhcyBwYXNzZWQgYXMgYSBiYXNlNjQgZW5jb2RlZCBmaWxl"
        }
    ]
}
```

* `compiler` defaults to `pdflatex`. Available compilers: `pdflatex`, `xelatex`, `lualatex`, `platex`, `uplatex` and `context`.
* `resources` entries:
    * These are the files uploaded and to be compiled;
    * There must be an entry for the [main LaTeX document](https://en.wikibooks.org/wiki/LaTeX/Modular_Documents), tagged with the `main: true` value; if there is only one entry, it is considered the main document;
    * Resource entries that are not the main document must be specified a `path`, relative to main document; these files can then been referred in the LaTeX sources;
    * There are several resource content formats:
        * String format, with `content` (value must be encoded as a valid Json string);
        * Inline file format, with `file` (value must be [base64](https://en.wikipedia.org/wiki/Base64) encoded)
        * URL to a file, with `url` (the resource pointed by the URL will be downloaded and decoded with UTF-8).
* `options` properties:
    * `options.compiler.bibliography` to enable Latexmk [`-bibtex` option](https://man.archlinux.org/man/latexmk.1#bibtex) (run bibtex or biber
    as needed to regenerate bbl files). Default to `true`.
    * `options.compiler.halt_on_error` to enable `-halt-on-error` option (stop on first error, even if non fatal). Default to `false`.
    * `options.compiler.silent` to enable `-interaction=batchmode` option and Latexmk `-silent` (non verbose mode). Default to `false` (will use `-interaction=nonstopmode`).
    * `options.compiler.force` to enable Latexmk [`-f` (force mode)](https://man.archlinux.org/man/latexmk.1#f). Default to `true`.
    * `options.response.log_files_on_failure` to return full log files on compilation error. Defaults to `true`.
    * `options.response.commands` to return commands run details. Defaults to `false`.


> Response

A PDF file if the compilation succeeds, else a Json payload with the error logs.

## Inspecting build environment (texlive, fonts, packages)

### `GET:/texlive/information`

See information on TeXLive installation used in LaTeX compilations.

>  Request

`GET:/texlive/information`


>  Response

A Json payload with a TeXLive installation specification.

Sample
```json
{
  "texlive": {
    "installation_path": "/usr/local/texlive", 
    "modules": [
      {
        "name": "TLConfig", 
        "value": "52745"
      }, 
      ["..."]
    ], 
    "version": "2019"
  }, 
  "tlmgr": {
    "revision": "52931", 
    "revision_date": "2019-11-27 00:04:18 +0100"
  }
}
```

### `GET:/fonts`

Explore available fonts that can be used directly in LaTeX compilations.

>  Request

`GET:/fonts`

>  Response

A Json payload with a list of fonts.

Sample
```json
{
  "fonts": [
    {
      "family": "Courier New",
      "name": "Courier New",
      "styles": [
        "Regular"
      ]
    },
    ["..."]
}
```

### `GET:/packages`

Explore installed LaTeX packages that can be used in compilations.

>  Request

`GET:/packages`

>  Response

A Json payload with a list of packages.

Sample
```json
{
  "packages": [
    {
      "installed": true, 
      "name": "12many", 
      "shortdesc": "Generalising mathematical index sets", 
      "url_ctan": "https://ctan.org/pkg/12many", 
      "url_info": "/packages/12many"
    }, 
    ["..."]
}
```

### `GET:/packages/<packgeName>`

Get information on a LaTeX package, including whether it is installed or not.

>  Request

`GET:/packages/<packageName>`

>  Response

A Json payload with information on the package.

Sample for `/packages/12many`
```json
{
  "package": {
    "cat-date": [
      "2016-06-24T19:18:15+02:00"
    ],
    "cat-license": "lppl",
    "cat-topics": [
      "maths"
    ],
    "cat-version": "0.3",
    "category": "Package",
    "collection": "collection-mathscience",
    "installed": true,
    "longdesc": "In the discrete branches of mathematics and the computer sciences, it will only take some seconds before you're faced with a set like {1,...,m}. Some people write $1\\ldotp\\ldotp m$, others $\\{j:1\\leq j\\leq m\\}$, and the journal you're submitting to might want something else entirely. The 12many package provides an interface that makes changing from one to another a one-line change.",
    "package": "12many",
    "relocatable": false,
    "revision": "15878",
    "shortdesc": "Generalising mathematical index sets",
    "sizes": {
      "run": "5k"
    },
    "url_ctan": "https://ctan.org/pkg/12many"
  }
}
```

# Docker

## Images

Prebuilt Docker images exist to run the service on your own:
* The Python+TexLive near complete LaTeX-on-HTTP image: [yoant/latexonhttp-python](https://hub.docker.com/r/yoant/latexonhttp-python)
* The base TexLive image: [yoant/docker-texlive](https://hub.docker.com/r/yoant/docker-texlive)

## Run the service

You can use the default [`docker-compose.yml`](https://github.com/YtoTech/latex-on-http/blob/master/docker-compose.yml):

```sh
docker-compose up
```

The service will be available on http://localhost:2345.

# Starred Use cases

## Max Model [Interactive TikZ Editor](https://max-models.github.io/tikzfigure/editor/)

A [Tikz visual editor](https://max-models.github.io/tikzfigure/tikz-editor.html) for generating Python or LaTeX Tikz code for several style of figures.

## Yann Barsamian [Maths Exams](https://www.barsamian.am/mathsexams/)

Yann Barsamian uses LaTeX-on-HTTP to compile PDFs of its [Math Exam database](https://www.barsamian.am/mathsexams/) (sources not open).

## Repository [Examples](/examples/)

Look at the repository set of examples, that showcase usages from Curl, HTTPie, GitLab CI, etc.

----------------------------------

## Credits

Inspired by:
* [Overleaf](https://www.overleaf.com/) and [Sharelatex](https://fr.sharelatex.com/) for the idea that LaTeX can be made a web-accessible tool
* ... and for their open-source cloud LaTeX compiling architectures ([clsi-sharelatex](https://github.com/sharelatex/clsi-sharelatex) and [clsi-overlead](https://github.com/overleaf/clsi))
* [Latex-Online](https://github.com/aslushnikov/latex-online) from aslushnikov for a CLI-oriented online LaTeX compiler
* mrzool for its [great LaTeX templates](http://mrzool.cc/writing/typesetting-automation/) and integration with Pandoc
