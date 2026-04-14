# Ship Runbook

Use this when preparing a branch for PR creation or merge.

## Read first

1. `docs/PLAN.md`
2. `docs/learn/README.md`
3. `docs/learn/prs/README.md`

## Required output

Return:

1. A ship-readiness checklist with `done / not done / not verified`
2. Any missing prerequisites
3. Suggested next commands, but do not execute risky git operations silently

## Checklist

- Tests/checks were run, or the response explicitly says they were not run
- The branch follows the relevant phase constraints in `docs/PLAN.md`
- `docs/learn/prs/pr-NNN-<slug>.md` exists when the PR number is known
- `docs/learn/journey.md` and any matching learning docs are updated only when
  the repo's own rules permit it
- Root tool adapters, `docs/ai/README.md`, and runbooks do not contradict one
  another

## Git safety

- Do not auto-squash
- For any history rewrite (squash, rebase, `reset --soft`, force-push), explain
  the exact commands you would run and ask the user for explicit approval first
- Do not assume `gh` is configured or that a PR number already exists
