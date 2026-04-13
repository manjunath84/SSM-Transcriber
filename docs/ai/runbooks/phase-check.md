# Phase Check Runbook

Audit the current branch against Phase 1 Foundations (F1–F8).

## Read first

Read the Phase 1 Foundations section in `docs/PLAN.md` directly before
auditing. Do not restate the contracts from memory.

## Required output

Produce a Markdown table with:

| Contract | Status | Evidence | Remediation |
|----------|--------|----------|-------------|

Use `PASS`, `FAIL`, or `N/A`.

## What to inspect

| Contract | Inspect |
|----------|---------|
| F1 | `async def` use in pipeline/source/provider/formatter code |
| F2 | Source boundary and `PreparedMedia` usage |
| F3 | Cache-key inputs and invalidation strategy |
| F4 | Spend gating and cost-confirmation flow |
| F5 | `RunWorkspace`, temp-file ownership, atomic writes |
| F6 | First-run model download visibility |
| F7 | Fixtures, stubs, and integration-test gating |
| F8 | `print()`, `os.environ`, full settings dumps, and logging hygiene |

