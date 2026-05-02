# PR #9 — Mission: provider-agnostic framing with default-cheap

**Merged:** TBD  |  **Branch:** `docs/mission-provider-agnostic-framing`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-9--mission-provider-agnostic-framing-with-default-cheap`](../journey.md#pr-9--mission-provider-agnostic-framing-with-default-cheap)

## The problem in one paragraph

The mission statement landed in PR #8 led with "SSM-Transcriber is a
**local-first** audio/video transcription pipeline." That phrasing was
inherited from older repo language and was doing two jobs at once: stating
a *cost philosophy* (zero-cost-by-default) and stating a *project identity*
(local is the canonical path; cloud is the exception). The cost philosophy
is uncontroversial and stays. The identity claim was starting to constrain
the future — the user has a clear interest in head-to-head accuracy and
cost comparison across providers (faster-whisper vs AssemblyAI vs Deepgram
vs OpenAI Whisper), and that goal sits awkwardly under a "local-first
always" identity. This PR reframes the mission so the cost protection
stays but the asymmetric framing goes.

## What changed (high level, not file-by-file)

- `specs/mission.md` "What this is" — rewrites the lead from "local-first"
  to "provider-agnostic where **accuracy is the primary deciding factor**,
  **cost is the gating constraint**, and **convenience is a legitimate
  tiebreaker**." Local and hosted providers are now described as
  first-class peers; the user typically picks the most accurate provider
  that fits the budget, but may opt for a different provider for
  convenience (familiar API, already-configured auth, an existing
  workflow). The default-cheap behavior (`--budget free` → `$0`) and the
  two-gate spend protection are preserved verbatim.
- `specs/mission.md` "In scope" — adds a bullet recording that head-to-head
  evaluation of providers on accuracy *first*, then cost, is a stated
  future direction and is intended to drive subsequent provider and
  default choices. The MVP's choice of AssemblyAI as the first hosted
  provider is recorded as provisional pending those evaluations, with
  accuracy as the primary tiebreaker.
- Per-PR teaching artifacts: this explainer, the journey entry, the
  prs/README index row.

## Why this approach

The user explicitly chose "provider-agnostic, default-cheap" over two
alternatives: (a) a stricter "equal first-class" framing that fully drops
local-as-default, and (b) a more ambitious framing that explicitly commits
to a comparison feature. Option B preserves the zero-cost protection that
matters in practice (one accidental click won't bill the user) while
removing the *moral* asymmetry that would make the comparison vision look
inconsistent with the project's identity.

Mid-draft, the user refined the framing three times: first elevating
**accuracy** alongside cost as a first-class deciding factor, then
clarifying that accuracy is in fact the *primary* deciding factor with
cost serving as the gating constraint, then adding **convenience** as a
legitimate tiebreaker. The reasoning: "cheapest" alone is not a sound
reason to pick a transcription provider — accuracy on real source material
comes first; cost determines whether a paid option is available at all
(via the two-gate spend), not which paid option to pick when several pass
the budget; and a real human user will reasonably reach for a provider
they already have wired up rather than the strict accuracy-cost optimum.
The MVP's AssemblyAI choice is therefore recorded as provisional, pending
future head-to-head evaluations across providers — with explicit room for
convenience-driven choices once the accuracy/cost data is in hand.

The mission file is the *summary*, not a contract. Per
`specs/README.md`, technical contracts live in `docs/PLAN.md`. This change
does not touch any contract; it only updates the elevator pitch.

## New Python idioms introduced

None — this PR is doc-only.

## New AI/ML concepts introduced

None — the underlying concepts (`provider abstraction`,
`two-gate spend model`) were already in the glossary.

## What a reviewer should notice

- The PR is **doc-only**; no `src/` changes.
- The two-gate spend model is preserved verbatim. The default budget
  remains `free`. Casual use still costs `$0`. Anyone scared the
  comparison framing weakens the spend protection should re-read the
  "What this is" paragraph: every cloud call still requires a configured
  key, an explicit `--budget low|best`, AND cost confirmation.
- `docs/PLAN.md` still contains a "Local-first, always" line under its
  "Cost Optimization Strategy" section. That line reads as a *strategy
  principle* (default to zero-cost local processing) rather than the
  project identity, so it is internally consistent with the new mission
  framing — but it is the next thing worth revisiting if PLAN.md is
  edited for any reason. Not addressed in this PR; flagged for future
  cleanup.
- This PR was opened on its own branch, separate from the in-flight
  `feature/assemblyai-mvp-slice-1` branch (whose spec files are
  stashed). That follows the user's SDD rule: "Keep constitution updates
  on their own branch when possible."

## Interview angle

- **Story type:** trade-off / framing decision.
- **One-sentence hook:** "Reframing the project identity from
  'local-first' to 'provider-agnostic, default-cheap' to unblock future
  multi-provider comparison work — without weakening the cost protection
  that matters in practice."
- **Pointer:** `interview-prep.md` — workflow design / agentic-engineering
  section (entry to be added when interview-prep is next refreshed).

## Further reading

- [`specs/mission.md`](../../../specs/mission.md)
- [`docs/PLAN.md`](../../PLAN.md) §Context and §Cost Optimization Strategy
- [`pr-008-adopt-sdd-constitution.md`](pr-008-adopt-sdd-constitution.md) — the prior PR that introduced this mission file.
