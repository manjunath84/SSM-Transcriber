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

## Architecture checks

- No `async def` on pipeline, source, provider, or formatter code before Phase 5
- No direct `os.environ` access under `src/transcriber/`
- No `print()` in library code
- No transcript cache keyed on just file hash + quality
- Cloud/API calls respect the two-gate spend model
- Temp artifacts flow through `RunWorkspace`; atomic writes use a temp file in
  the destination directory
- VAD stays a sidecar, not a destructive transform of canonical audio

## Docs/process checks

- Living docs only document concepts that exist and can cite real repo
  locations
- Runbooks and command files do not invent policy that conflicts with
  `docs/PLAN.md` or `docs/learn/README.md`
- Tool-specific adapter files stay compact, but still contain enough inline
  guidance to avoid obvious first-turn mistakes

## Review mindset

- Findings first; summary second
- Focus on bugs, churn risk, behavioral regressions, stale docs, and workflow
  hazards
- For doc-only PRs, internal consistency is the primary quality bar

