# CLAUDE.md

Rendering worker for the Endleaf product: turns Markdown/TikZ or a TeX body into
PDF, HTML or DOCX inside a per-job sandbox. It is an AGPL-3.0 fork of
YtoTech/latex-on-http (see `NOTICE`); Python code is in `colophon/`.

## Commands

- Install: `make install` (uses `uv sync`; Python 3.12 or 3.13).
- Unit tests: `make test` (`uv run pytest -vv`), the same as CI. `pytest.ini`
  deselects the `integration` and `podman` markers by default.
- Last local run: 416 passed, 177 skipped, 35 deselected, 1 failed
  (`tests/colophon/test_sysml_tikz.py::test_vendored_style_matches_endleaf_and_requires_only_tikz`,
  a sha256 check of the vendored `.sty`; it also fails on a clean checkout).
- Skips: tests that need TeX Live, Pandoc, rootless podman or the built image
  skip themselves when the tool is missing. `-m integration` needs a running
  server; `-m podman` needs podman plus the worker image. Both are off by default.
- Run the worker: `make start` (`python -m colophon`); `make preflight` checks the host.
- Format: `make format` (black).
- Image: `container/Dockerfile.endleaf` (see README.md). The TeX/Docker build is
  heavy; prefer unit tests that run without it, and do not build it unless the task needs it.
- Never do live renders or call a live endpoint from an agent run.

## Layout

- `colophon/` worker code: HTTP entry, render plan, sandbox runner, limits, TeX log parsing.
- `colophon/share/` templates, TeX preambles and styles, podman hooks, diagram lock.
- `latexonhttp/`, `app.py`, `app_cache.py` upstream latex-on-http API and cache app.
- `container/` image Dockerfiles, package-set bake, sandbox wrapper scripts, fixture runners.
- `vendor/` vendored third-party sources (`diagram`, `pidcircuittikz`); each has its own README.
- `tests/` pytest suites; `tests/colophon/` covers the worker, `tests/colophon/fixtures/` holds TeX fixtures.
- `scripts/` negative-test helper; `examples/`, `samples/`, `tools/` upstream leftovers.
- `.github/workflows/` unit tests, arm64 image CI, image publish.

## Conventions

- Design requirements live in the Endleaf product repo under `sysml-models/`.
  Change the model first, then the worker code.
- Requirement ids follow `ENDLEAF-Rnn` (optionally with a suffix such as
  `-FIT` or `-SYMBOLS`). Put the id in the commit subject and PR title, e.g.
  `Worker: circuitikz 1.8.7 in the image (ENDLEAF-R75)`; PRs get `(#nn)` on merge.
- Every behavior change adds a `CHANGELOG.md` entry at the top, headed
  `## <date> (ENDLEAF-Rnn)`, with bullets that start with the id.
  Add or update a test under `tests/colophon/`.
- Branches: never commit to `master`, never force-push. Work on a branch and
  open a PR; a maintainer merges, not an agent.
- Keep secrets, keys, host names and IPs out of files, fixtures, commits and PRs.

## Source of truth (read, do not copy)

- `README.md` worker overview, image build, API notes. `DEV.md` short dev notes.
- `CHANGELOG.md` history by requirement id. `NOTICE` fork modifications.
- `Dockerfile`, `container/Dockerfile.endleaf` images. `colophon/` and `vendor/` code.
- `tests/` executable specification of worker behavior.
