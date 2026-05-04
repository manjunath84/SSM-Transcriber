# PR #7 — Backfill PR #6 merge date (TBD → 2026-05-01)

**Merged:** 2026-05-01  |  **Branch:** `docs/backfill-pr-6-merge-date`  |  **Codex review:** n/a (mechanical)
**Journey entry:** [`../journey.md#pr-7--backfill-pr-6-merge-date`](../journey.md#pr-7--backfill-pr-6-merge-date)

## The problem in one paragraph

PR #6 itself established the convention of backfilling `Merged: TBD`
placeholders with the actual merge date once a PR lands, applying it
to PR #4 and PR #5 in the same commit. After PR #6 merged, its own
journey entry and explainer header were left with `Merged: TBD`.
PR #7 is the smallest possible follow-up — a 2-line change that
applies the same convention to PR #6's own entries.

## What changed

- `docs/learn/journey.md` PR #6 entry: `Merged: TBD` → `Merged: 2026-05-01`.
- `docs/learn/prs/pr-006-roadmap-naming-and-hosted-provider-strategy.md`
  header: same backfill.

## Why a separate PR

PR #6 couldn't backfill its own merge date — by definition, the date
isn't known until *after* the merge. Doing it in a follow-up PR is the
documented pattern, not a missed opportunity. The same pattern applies
in this housekeeping PR retroactively to PR #12 and PR #13.

## What a reviewer should notice

- This is mechanical: 2 lines changed, both `TBD` → an ISO date.
- No code, no convention change, no behaviour change. CI green by
  default.
- The pre-existing learning-artifact gap (this very explainer file
  wasn't drafted alongside PR #7 at the time) has been flagged across
  PRs #6, #8, #10, #12, #13. This file closes that gap retroactively;
  it was added during the housekeeping bundle in the PR after #13.

## Further reading

- [`pr-006-roadmap-naming-and-hosted-provider-strategy.md`](pr-006-roadmap-naming-and-hosted-provider-strategy.md) — the convention this PR continues.
