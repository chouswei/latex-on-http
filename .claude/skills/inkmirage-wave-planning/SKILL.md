---
name: inkmirage-wave-planning
description: Use when planning, running or reviewing a multi-step InkMirage build job in Claude Code (sonnet plans, haiku builds, sonnet reviews), before reading any source files or writing a plan.
---
# InkMirage wave planning

Roles (sonnet plans and reviews, haiku builds, owner merges): see team-work-cycle; not repeated here. Rows live in the job's Atelier session (see atelier-working-memory).

## Plan in small turns (F1/F2)
1. **Digest first (F2).** A haiku wave reads the source docs, one doc per agent, and writes one short `digest` row per doc: purpose, the facts the task needs, and the **file and line ranges** each fact came from. Digests can be wrong or incomplete; when in doubt, the planner opens that source range.
2. **Skeleton (F1).** In one short turn, write the plan as `task` rows, a title and one line each.
3. **Expand one row per turn (F1).** Detail one row (files, steps, acceptance check), write it, end the turn. Open source only for that row, only the named line range.
4. **Wave.** Haiku builders take expanded rows; each writes a `done` or `blocker` row. No two in a wave touch the same files.
5. **Review.** Sonnet reviews from done rows and diffs, writes the next wave. Then one PR.

## Short turns
- One turn = one digest, one skeleton, one row, or one review. Short turns also keep the prompt cache warm.
- The stall guard lives in the claude-sub wrapper (no-output guard F4 + explicit request timeout F3), not here. Until those are set, short turns are the only defense.
- If the same task fails twice, write a blocker row and stop.
- Opus is allowed with small turns, but it does not fix the stall.
- Numeric caps are not set; they go in the wrapper after the three test runs. Do not invent them.
