# CLAUDE.md (latex-on-http, InkMirage repo)

Read digest rows, not source docs.

This is the only always-loaded copy of these rules. Skills (in this repo's .claude/skills):
- **inkmirage-change-rules**: who saves and merges, git limits, command form, naming, build pattern.
- **inkmirage-secrets-hygiene**: keys and codes by path only; what to do on a leak.
- **inkmirage-wave-planning**: any multi-step job. Digest rows, skeleton plan, one row per turn.
- **atelier-working-memory**: reading and writing task, done and blocker rows.
- Architecture map: `docs/ARCHITECTURE.md` in inkmirage-account (open only if a value you need is missing here).

## Short version
- The saved model on the SysMLEdge desk comes first; this repo follows it. Desk or folder: the owning product desk (Endleaf for render/client repos).
- If this text and the saved desk model disagree, the desk wins; write a blocker row.
- Work on a branch. Never merge, never push to main, never force-push. One PR at the end; the owner merges.
- Only the owner's own "save" or "merge" counts. A relayed go does not.
- Short turns: one digest, one skeleton, one row per turn. Never plan in one giant turn.
- If the same task fails twice, write a blocker row and stop.
- Never put keys, codes, tickets or tokens in rows, prompts, commits, PRs or output.
- Name the operator only as "InkMirage", contact support@inkmirage.xyz.

## This repo
- Product: Endleaf render worker (AGPL-3.0 fork of YtoTech/latex-on-http)
- Runs on: Rootless container on the render host, reached only from the Endleaf gateway
- Tests: `uv run pytest`, run from the repo root (Python, uv)
- Do not touch: `vendor/`; sandbox rules win over upstream
