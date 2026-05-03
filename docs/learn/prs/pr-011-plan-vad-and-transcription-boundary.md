# PR #11 — PLAN: tighten VAD framing and Phase 1 transcription boundary

**Merged:** TBD  |  **Branch:** `docs/plan-vad-and-transcription-boundary`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-11--plan-tighten-vad-framing-and-phase-1-transcription-boundary`](../journey.md#pr-11--plan-tighten-vad-framing-and-phase-1-transcription-boundary)

## The problem in one paragraph

Two small but real inconsistencies in `docs/PLAN.md` were spotted while
the AssemblyAI Slice 1 implementation was being scoped. First, the cost
table line for "Cloud audio upload size" said *"Strip silence with VAD
before upload (saves 20–40% duration)"* — which contradicts the
elsewhere-stated principle "VAD is a sidecar only; do not strip canonical
audio before transcription" (F-cost-section item 3, restated in
`CLAUDE.md`). The cost table line implied the canonical upload would be a
silence-stripped audio stream, which would also break sentence-level
timestamp alignment with the original media. Second, the Phase 1
transcriber file (`src/transcriber/core/transcriber.py`) was described as
a direct `faster-whisper` wrapper with no boundary/interface — so sources
calling it would couple straight to the local implementation, making the
later Phase 5 provider abstraction harder than necessary. The
in-flight AssemblyAI Slice 1 spec (PR #10) is already defining a thin
`TranscriptionProvider` boundary for the cloud side; Phase 1's local
side should mirror that shape from the start.

## What changed (high level, not file-by-file)

- `docs/PLAN.md` cost table — "Strip silence with VAD before upload" →
  "Optimize VAD at transcription engine level (preserve timestamps)".
  Aligns the cost story with the existing canonical-audio-preserved
  principle.
- `docs/PLAN.md` Phase 1 file list — adds an explicit "define a minimal
  transcription boundary/interface here early. Implement the
  `faster-whisper` wrapper behind this interface so sources do not
  tightly couple to the implementation." Phase 5's provider abstraction
  becomes a *generalization* of this Phase 1 boundary rather than a
  rewrite that has to thread back through Phase 1 callers.
- `docs/PLAN.md` Critical Files table row updated to match: "faster-whisper
  wrapper" → "Transcription boundary + faster-whisper wrapper".

## Why this approach

Both edits are *internal-consistency* fixes — they don't change what any
phase ships, they change how each phase is described so the description
matches the principles already binding elsewhere. The VAD line in the
cost table was a leftover from an older "strip-then-upload" cost-saving
plan that the F-cost-section already moved away from; this PR closes that
last reference. The Phase 1 transcriber boundary note doesn't add work
in Phase 1 (still a `faster-whisper` wrapper), it just makes the abstraction
explicit so the Phase 5 generalization is additive rather than a refactor
of every existing call site.

The PR is deliberately tiny (3 single-line edits). It lives on its own
branch per SDD's "constitution updates on their own branch when possible"
rule — exactly the same pattern PR #9 followed for the mission reframe.

## New Python idioms introduced

None — this PR is doc-only.

## New AI/ML concepts introduced

None — `VAD` and `provider abstraction` already live in the glossary.

## What a reviewer should notice

- The PR is **doc-only**; only `docs/PLAN.md` changes (3 single-line
  edits) plus per-PR teaching artifacts.
- Neither edit changes any phase's deliverable. They tighten the
  description so it matches principles already binding elsewhere in
  PLAN.md and in `CLAUDE.md`.
- The VAD edit removes the last "strip silence before upload" reference
  in PLAN.md. After this PR, the only VAD framing left is "sidecar only;
  used for cost estimation and reduced-upload optimization at the
  *transcription engine* level," which is consistent across the cost
  table, the F-section, and `specs/tech-stack.md`.
- The Phase 1 transcription-boundary note runs in the same direction as
  the in-flight AssemblyAI Slice 1 implementation (which defines a thin
  `TranscriptionProvider` ABC for the cloud provider). That is
  intentional: Phase 1 (local) and Phase 5 (cloud) end up with the same
  abstraction shape, with Phase 5 being the *generalization* that adds
  the `--budget` routing and cost-estimation hook, not a rewrite.

## Interview angle

- **Story type:** internal-consistency / doc-as-architecture.
- **One-sentence hook:** "Two single-line PLAN edits that prevented a
  real Phase 1 refactor down the road by making the transcription
  boundary explicit *before* the first wrapper was written, while a
  separate edit removed a stale 'strip-before-upload' reference that
  conflicted with the canonical-audio-preserved principle."
- **Pointer:** `interview-prep.md` — workflow design / agentic-engineering
  section (entry to be added when interview-prep is next refreshed).

## Further reading

- [`docs/PLAN.md`](../../PLAN.md) §Cost Optimization Strategy + §Phase 1 + §Critical Files — the three sections this PR edits.
- [`docs/learn/glossary.md`](../glossary.md) entries for `VAD` and `provider abstraction`.
- [`pr-006-roadmap-naming-and-hosted-provider-strategy.md`](pr-006-roadmap-naming-and-hosted-provider-strategy.md) — prior PR that cleaned up the same kind of internal-consistency drift in PLAN.md.
- [`pr-009-mission-provider-agnostic-framing.md`](pr-009-mission-provider-agnostic-framing.md) — prior constitution-on-its-own-branch precedent.
- [`pr-010-assemblyai-mvp-slice-1-spec.md`](pr-010-assemblyai-mvp-slice-1-spec.md) — the AssemblyAI Slice 1 spec whose thin-boundary approach Phase 1 is being aligned with here.
