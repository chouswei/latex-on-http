---
name: inkmirage-secrets-hygiene
description: Use whenever an InkMirage task involves a key, token, session code, bind ticket or owner key, including binding Atelier, writing rows, prompts, logs or PRs, or when a secret may have leaked.
---
# InkMirage secrets hygiene

- Secrets live only in files under `/home/box/.claude-login/`. Refer to them by path; never open, print or grep them.
- Secrets include Atelier session codes, owner keys, bind tickets, MemNet session ids, MCP bearer tokens.
- Never put one in rows, prompts, plans, PRs, commits, fixtures, logs, command lines or output. Write `[REDACTED]` or the path.
- Bind Atelier once per session; then pass the ticket, never the code, and never hand a ticket to another agent. (Bind by reference is later server/wrapper work.)

## If a secret leaks
1. Stop. Do not repeat it, quote it or "show where it is".
2. Write a blocker row with the kind of secret and where it appeared (file, PR, row id, log) and when; never the value.
3. Tell the owner. Rotation is the owner's decision; do not rotate on your own.
4. Never force-push to clean history; removing it from a pushed branch or PR needs the owner's go.
