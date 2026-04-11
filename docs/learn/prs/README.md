# PR Explainers

> Human-readable per-PR changelog. One file per merged PR, named
> `pr-NNN-<slug>.md`, using the template in
> [`../README.md`](../README.md#pr-explainer-template). Written **before**
> the PR is opened so the PR body can link to it.

## Index (chronological, oldest first)

| PR | Title | Phase | Explainer |
|----|-------|-------|-----------|
| #1 | Phase 0 — project skeleton | 0 | [`pr-001-phase-0-skeleton.md`](pr-001-phase-0-skeleton.md) |
| #2 | Phase 0 — rename to SSM-Transcriber | 0 | [`pr-002-phase-0-rename.md`](pr-002-phase-0-rename.md) |
| #3 | Phase 1 Foundations (F1–F8) | 1 (plan) | [`pr-003-phase-1-foundations.md`](pr-003-phase-1-foundations.md) |
| #4 | `docs/learn/` + teaching register | — | [`pr-004-docs-learn-teaching-register.md`](pr-004-docs-learn-teaching-register.md) |

## Conventions

- **Stubs vs. fresh entries.** PRs #1 and #2 predate this folder, so their
  explainers are short retrospective stubs. Every PR from #3 onward is
  written to template *before* the PR is opened.
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
