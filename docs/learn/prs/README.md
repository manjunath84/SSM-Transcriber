# PR Explainers

> Human-readable per-PR changelog. One file per PR, named
> `pr-NNN-<slug>.md`, using the template in
> [`../README.md`](../README.md#pr-explainer-template). Drafted **before**
> the PR is opened so the PR body can link to it. If the number is not known
> yet, draft the content first and write the numbered file once the number
> exists; update `Merged:` after merge.

## Index (chronological, oldest first)

| PR | Title | Phase | Explainer |
|----|-------|-------|-----------|
| #1 | Phase 0 — project skeleton | 0 | [`pr-001-phase-0-skeleton.md`](pr-001-phase-0-skeleton.md) |
| #2 | Phase 0 — rename to SSM-Transcriber | 0 | [`pr-002-phase-0-rename.md`](pr-002-phase-0-rename.md) |
| #3 | Phase 1 Foundations (F1–F8) | 1 (plan) | [`pr-003-phase-1-foundations.md`](pr-003-phase-1-foundations.md) |
| #4 | `docs/learn/` + teaching register | — | [`pr-004-docs-learn-teaching-register.md`](pr-004-docs-learn-teaching-register.md) |
| #5 | AI operator guide + workflow commands | infra | [`pr-005-ai-operator-guide-workflow-commands.md`](pr-005-ai-operator-guide-workflow-commands.md) |
| #6 | Roadmap naming cleanup + hosted-provider strategy | docs | [`pr-006-roadmap-naming-and-hosted-provider-strategy.md`](pr-006-roadmap-naming-and-hosted-provider-strategy.md) |
| #7 | Backfill PR #6 merge date | docs (mechanical) | [`pr-007-backfill-pr-6-merge-date.md`](pr-007-backfill-pr-6-merge-date.md) |
| #8 | Adopt SDD: bootstrap project constitution under `specs/` | infra | [`pr-008-adopt-sdd-constitution.md`](pr-008-adopt-sdd-constitution.md) |
| #9 | Mission: provider-agnostic framing with default-cheap | docs | [`pr-009-mission-provider-agnostic-framing.md`](pr-009-mission-provider-agnostic-framing.md) |
| #10 | Feature spec: AssemblyAI MVP Slice 1 | feature (spec) | [`pr-010-assemblyai-mvp-slice-1-spec.md`](pr-010-assemblyai-mvp-slice-1-spec.md) |
| #11 | PLAN: tighten VAD framing and Phase 1 transcription boundary | docs | [`pr-011-plan-vad-and-transcription-boundary.md`](pr-011-plan-vad-and-transcription-boundary.md) |
| #12 | Implementation: AssemblyAI MVP Slice 1 | feature (impl) | [`pr-012-assemblyai-mvp-slice-1-impl.md`](pr-012-assemblyai-mvp-slice-1-impl.md) |
| #13 | Prevent vendor-API-shape regressions: SDD template + mock convention | infra | [`pr-013-prevent-vendor-api-shape-regressions.md`](pr-013-prevent-vendor-api-shape-regressions.md) |
| #14 | Housekeeping: merge-date backfills + roadmap Phase 5 update + PR-7 explainer | docs | [`pr-014-housekeeping-merge-dates-roadmap-pr7-explainer.md`](pr-014-housekeeping-merge-dates-roadmap-pr7-explainer.md) |
| #15 | Feature spec: Drive Source (URL passthrough) | feature (spec) | [`pr-015-drive-source-passthrough-spec.md`](pr-015-drive-source-passthrough-spec.md) |
| #16 | Execution plan: Drive Source (URL passthrough) | feature (plan) | (no explainer — short doc-only PR; see plan triple) |
| #17 | Implementation: Drive Source (URL passthrough) | feature (impl) | [`pr-017-drive-source-passthrough-impl.md`](pr-017-drive-source-passthrough-impl.md) |

## Conventions

- **Stubs vs. fresh entries.** PRs #1 and #2 predate this folder, so their
  explainers are short retrospective stubs. Every PR from #3 onward is
  drafted to template *before* the PR is opened and has its `Merged:` line
  updated after merge.
- **Retrospective explainers are a documented pattern, not a silent
  exception.** When an explainer is missed at merge time, it gets
  backfilled in a later PR with a brief note about why (PR #7's was
  backfilled in PR #14 because the original was 2 lines of mechanical
  change; PR #14's own explainer was backfilled in PR #15's review
  cycle because the housekeeping bundle's nature wasn't immediately
  obvious as warranting one). The default is still draft-before-open;
  retrospective backfill is the documented recovery, not a habit.
- **"Explainer" is not "summary".** A summary tells you what changed. An
  explainer tells you what problem existed, why this approach, and what a
  Java dev new to Python should take away from it.
- **Cross-linking is mandatory.** Every explainer links to the matching
  `journey.md` entry, relevant `python-notes.md` sections, relevant
  `glossary.md` entries, and — if the PR ships a decision worth talking
  about — the matching section in [`../interview-prep.md`](../interview-prep.md).
  Broken links are a review blocker.
- **Interview angle is optional but encouraged.** If the PR lands an
  architectural choice, a trade-off, a bug caught before shipping, or a
  boundary design, fill in the "Interview angle" section of the template.
  Mechanical PRs (renames, dependency bumps, typo fixes) should leave the
  section out entirely.
