# AGENTS.md

Agent context for this repository lives in [CLAUDE.md](CLAUDE.md); read it first.
It covers commands, layout, conventions and source-of-truth pointers.

Notes for Cursor and other agents:

- Run `make test` before proposing a change; it needs only Python and `uv`.
- Docs-only or small changes: do not build the TeX/Docker image.
- Do not render against live endpoints.
- Commit on a branch, never to `master`, no force-push; leave merging to a maintainer.
- Reference requirement ids as `ENDLEAF-Rnn` in commits and `CHANGELOG.md`.
