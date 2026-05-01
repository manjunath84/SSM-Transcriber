# PR #6 — Roadmap naming cleanup and hosted-provider strategy

**Merged:** TBD  |  **Branch:** `codex/docs-stale-naming-cleanup`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-6--roadmap-naming-cleanup-and-hosted-provider-strategy`](../journey.md#pr-6--roadmap-naming-cleanup-and-hosted-provider-strategy)

## The problem in one paragraph

Several docs were already drifting away from the repo's actual decisions. The
rename follow-up still talked as if the `SSM-Transcriber` versus `transcriber`
split were unresolved, some roadmap examples still mixed old CLI wording with
the newer `uv run ssm-transcriber ...` form, and the Phase 5 provider story
was half on "fixed `cost_per_minute` property" language even though the
roadmap now needed room for providers whose pricing is variable or only
partially knowable up front. On a repo that expects multiple AI tools to read
these docs as source material, that kind of drift is how a doc-only mismatch
turns into the next implementation PR coding the wrong boundary.

## What changed (high level, not file-by-file)

- Cleaned up stale naming and source-of-truth wording in `README.md` and
  `docs/PLAN.md`
- Reframed Phase 5 around a shared transcription contract plus a richer
  provider-specific cost-estimation hook instead of a single fixed scalar
- Documented Hugging Face as a later experimental hosted-provider candidate
  that starts explicit-only and stays out of automatic `low` / `best` routing
- Updated the teaching docs (`glossary.md`, `interview-prep.md`,
  `python-notes.md`) so they match the current roadmap language
- Added the missing PR #6 learning artifacts and repaired older `Merged: TBD`
  / journey drift discovered during the review pass

## Why this approach

This PR deliberately stays doc-only. The goal is not to sneak in a Phase 5
implementation decision through prose; it's to make the source docs accurately
describe the constraints future code has to honor. The naming split remains
deliberate: users see `ssm-transcriber`, Python code keeps the shorter
`transcriber` namespace. The provider boundary also stays deliberate: local
first, `$0` by default, with hosted providers behind the same two-gate spend
rules whether their pricing is fixed or more nuanced.

The Hugging Face note is intentionally conservative. It acknowledges a real
future integration path without pretending the repo already trusts its backend
selection or spend predictability enough for automatic routing. That keeps the
docs honest and preserves the repo's "explicit paid choice" posture.

## New Python idioms introduced

- [`@property`](../python-notes.md#property) — the teaching note was updated
  so it no longer teaches an outdated Phase 5 API shape

## New AI/ML concepts introduced

- [`provider abstraction`](../glossary.md#provider-abstraction)
- [`two-gate spend model`](../glossary.md#two-gate-spend-model)

## What a reviewer should notice

- This is a doc-only PR, but it changes implementation guidance in a
  meaningful way by removing the assumption that every provider exposes a
  neat fixed `cost_per_minute`
- Hugging Face is documented as a later hosted-provider candidate, not as a
  default Phase 5 routing target
- The learning-doc artifacts are part of the fix: the PR is not "done" if the
  roadmap changes but the journey / explainer / teaching notes still tell the
  older story

## Interview angle

- **Story type:** trade-off / workflow design
- **One-sentence hook:** "I treated stale roadmap docs like an architecture
  bug, because multiple AI tools were using them to infer the wrong provider
  API and naming rules."
- **Pointer:** [`../interview-prep.md#how-do-you-ensure-ai-generated-code-follows-project-conventions`](../interview-prep.md#how-do-you-ensure-ai-generated-code-follows-project-conventions)

## Further reading

- [`docs/PLAN.md`](../../PLAN.md)
- [`../glossary.md#provider-abstraction`](../glossary.md#provider-abstraction)
- [`../python-notes.md#property`](../python-notes.md#property)
- [`pr-002-phase-0-rename.md`](pr-002-phase-0-rename.md)
