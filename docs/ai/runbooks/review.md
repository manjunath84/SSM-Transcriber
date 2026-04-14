# Review Runbook

Use this when reviewing a branch or diff before merge.

## Read first

1. `docs/PLAN.md` — especially Phase 1 Foundations (F1–F8)
2. `docs/learn/README.md` if the change touches `docs/learn/`, PR explainers,
   tool files, or other teaching-register content

## Required output

Return all three artifacts:

1. A prioritized findings list (`[P1]`, `[P2]`, `[P3]`) with file:line
   citations for every issue
2. An F1–F8 evidence table with `PASS`, `FAIL`, or `N/A`
3. Residual risks or testing gaps

## Audit method

- Read F1-F8 directly from `docs/PLAN.md` and audit the diff against those
  exact clauses. Do not restate the contracts from memory.
- If the change touches docs, PR workflow, tool adapters, or runbooks, read the
  relevant sections in `docs/learn/README.md` and `docs/learn/prs/README.md`
  directly before judging compliance.
- Cite concrete file:line evidence for each finding and for each row in the
  F1-F8 table.
- For doc-only PRs, internal consistency between source docs, adapters,
  runbooks, and commands is the main quality bar.

## Review mindset

- Findings first; summary second
- Focus on bugs, churn risk, behavioral regressions, stale docs, and workflow
  hazards
- For doc-only PRs, internal consistency is the primary quality bar
