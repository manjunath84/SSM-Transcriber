# PR #14 — Housekeeping: merge-date backfills, roadmap Phase 5 update, PR #7 explainer

**Merged:** 2026-05-04  |  **Branch:** `chore/housekeeping-merged-dates-pr7-explainer`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-14--housekeeping-merge-dates-roadmap-pr7-explainer`](../journey.md#pr-14--housekeeping-merge-dates-roadmap-pr7-explainer)

## The problem in one paragraph

Three small follow-ups had accumulated, each too small to ship as its
own PR but each with real value. PR #14 bundled them: backfill
`Merged: TBD` → actual dates on PR #12 and PR #13 entries (extending
the convention PR #7 itself established for PR #6); update
`specs/roadmap.md` Phase 5 status to mention PR #13's structural
defences alongside PR #12's implementation; finally write the long-
pending PR #7 explainer (the gap had been flagged across PRs #6, #8,
#10, #12, and #13). One commit, one PR, one review — instead of three
PRs each ceremoniously short.

## What changed (high level, not file-by-file)

- `docs/learn/journey.md` — `Merged: TBD` → `Merged: 2026-05-03` on
  PR #12 entry, → `Merged: 2026-05-04` on PR #13 entry.
- `specs/roadmap.md` Phase 5 — added a sentence pinning PR #13
  (structural defences: SDD `## Reference calls (verbatim)` template
  section + CLAUDE.md mock-fidelity / no-paraphrase guardrails)
  alongside the existing PR #12 mention. The phase is now framed as
  "AssemblyAI implementation **+** structural defences for future
  provider PRs," not just the implementation.
- `docs/learn/prs/pr-007-backfill-pr-6-merge-date.md` (new) — the
  retroactive explainer for PR #7 (the 2-line mechanical merge-date
  backfill that shipped without a learning artifact at the time).
- `docs/learn/journey.md` PR #7 entry (new — between PR #8 and PR #6
  in newest-first order) framing the same retroactive content.
- `docs/learn/prs/README.md` — index row for PR #7 added; convention
  text updated to name PR #7 as the *one-time retrospective
  exception* and explicitly reaffirm the default that future PRs
  draft their explainer before opening.

## Why this approach

The "bundle small housekeeping items together" pattern is rare but
correct when each follow-up is too small to warrant its own PR
overhead (commit + push + open PR + reviewer round-trip + merge
ceremony). The PR description was honest about the bundling — it
called out exactly three items, scoped each, and explicitly
documented one *deliberate* exclusion (Phase 1 Foundations status
update was flagged as a follow-up rather than expanded into).

The most interesting decision was the PR #7 explainer's *content*.
PR #7 was a 2-line mechanical merge-date backfill — there is no
"why this approach" worth telling. So the explainer's `## What a
reviewer should notice` section turns the meta-pattern itself into
the lesson: post-merge backfills are the *documented* convention,
not a missed step at merge time. A future contributor reading the
explainer learns the pattern, not the trivial fix.

## What a reviewer should notice

- **The bundling pattern is the unusual choice.** The convention
  default is one PR per concern; this PR has three. Worth doing only
  when each concern would otherwise be ceremony-heavy and the bundle
  has a unifying frame (here: "housekeeping that accumulated since
  PR #13 merged"). Not a precedent for routinely bundling unrelated
  work.
- **Codex review caught two Low findings on the original PR #14
  diff:** the PR #7 explainer named the wrong branch
  (`docs/backfill-pr-6-merge-date` vs the actual
  `chore/pr-6-merged-date-backfill`), and the `prs/README.md`
  convention text claimed "every PR from #3 onward drafted before
  opening" while this PR added PR #7's explainer retroactively. Both
  fixed in commit `aeeef44` before merge — the convention text now
  explicitly names PR #7 as the documented one-time retrospective
  exception.
- **This explainer itself is a *second* retrospective backfill.**
  PR #14's own explainer was missing at merge time (only flagged
  later by Codex review on PR #15 as a "second silent exception").
  This explainer closes that gap. The convention text in
  `prs/README.md` will need a one-line update in the next PR
  (likely PR #16 — Slice 2 implementation) to acknowledge that
  retrospective explainers are now the documented pattern for
  housekeeping bundles, not a one-time exception.

## Further reading

- [`pr-007-backfill-pr-6-merge-date.md`](pr-007-backfill-pr-6-merge-date.md) — the explainer this PR landed.
- [`pr-006-roadmap-naming-and-hosted-provider-strategy.md`](pr-006-roadmap-naming-and-hosted-provider-strategy.md) — the PR that established the merge-date backfill convention.
- [`pr-013-prevent-vendor-api-shape-regressions.md`](pr-013-prevent-vendor-api-shape-regressions.md) — the structural defences this PR added a roadmap pointer to.
