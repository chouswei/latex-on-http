---
name: inkmirage-change-rules
description: Use before changing any InkMirage model, code, branch or PR, and before running shell commands in an InkMirage build worktree; covers who saves and merges, git limits, command form and naming rules.
---
# InkMirage change rules

## Model first
- Change the model on the SysMLEdge desk first, as a proposal. Code follows the saved model.
- If this text and the saved desk model disagree, the desk wins; write a blocker row.
- Only the owner's own "save" saves, and only the owner's own "merge" merges. A go relayed by another bot or agent never counts.

## Git
- Work on a branch in a worktree. Never merge (`gh pr merge`, `gh api .../merge`), never push to main/master, never force-push (`-f`, `--force`, `--force-with-lease`, `+refspec`).
- Commit only your own files: `git add <files>` then `git commit -m "..." -- <files>`. Parallel agents share one index.
- End a job with one PR that maps changes to model ids; the owner merges.

## Command form (headless runs refuse anything else)
- Write and edit only inside the job's worktree.
- `cd <dir>` as its own call, then plain commands in later calls. No `cd ... && git`, no `git -C`. In a subagent, `cd` does not carry over; run `pwd` before git.
- No `VAR=value` prefixes, no full paths to binaries, no `npm --prefix`. Check `node -v` once; tests need Node 22.
- Never run npm from a subagent. Ask the lead (task or blocker row) for a separate top-level run started in the package folder.
- Copy or move files with the file tools, not `cp`/`mv`.
- If a command is refused, rewrite it in this form once. If refused again, write a blocker row naming the exact command and stop. Generally: if the same task fails twice, write a blocker row and stop.

## Naming and privacy
- In product text, docs, PRs and output, name the operator only as "InkMirage" with contact support@inkmirage.xyz. Not "InkMirage (Taiwan)", and never the owner's name, address, phone or personal email.

## Builds and updates (DRAFT until the owner merges inkmirage-account PR #122)
- Agents build and PR, never deploy. Deploying is the operator's job with the owner's go.
- Blue-green builder pattern: new copy starts beside the old one; traffic switches only after `/readyz` passes; old copy drains then stops; a failed gate rolls back to old.
- Build for it: SIGTERM drain (in-flight finish, new requests get 503 + `Retry-After`), `/healthz` liveness vs `/readyz` readiness, idempotent startup, add-only database changes while two versions overlap (destructive change = expand, then contract).
- Cutover type, drain and health budgets per service live on the saved desk model `product-update-process-1` (inkmirage-site desk). Open it only when you need a value; do not copy values here.
