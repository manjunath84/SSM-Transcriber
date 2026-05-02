# PR #10 — Feature spec: AssemblyAI MVP Slice 1

**Merged:** TBD  |  **Branch:** `feature/assemblyai-mvp-slice-1`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-10--feature-spec-assemblyai-mvp-slice-1`](../journey.md#pr-10--feature-spec-assemblyai-mvp-slice-1)

## The problem in one paragraph

After the SDD constitution landed (PR #8) and the mission was reframed
around accuracy / cost / convenience (PR #9), the next move under SDD is
to write the *first feature spec* before any code is written. The author
has ~$60 of existing AssemblyAI credit they want to utilise first, so
the natural first vertical slice is "local file → AssemblyAI → Markdown"
— paid-only by definition, but the cleanest way to validate the whole
paid-provider plumbing (two-gate spend, retry, polling, atomic write,
frontmatter) on a 30-second WAV before adding Drive OAuth on top. The risk: jumping straight
into implementation without a committed spec means drift between the
brainstorming we already did and the code that finally lands. SDD says
write the spec, commit it, *then* implement.

## What changed (high level, not file-by-file)

- New folder `specs/2026-05-02-assemblyai-mvp-slice-1/` with three files:
  - `requirements.md` — Goal / Non-goals / 11 numbered scenarios /
    constraints + decisions / output frontmatter contract / F1–F8 status
    table for this slice / dependencies added.
  - `plan.md` — 9 numbered task groups (deps, foundations, budget gate,
    provider, formatter, CLI, tests, teaching artifacts, exit gate). No
    function signatures or internal field names — those are
    implementation choices per the SDD "right level of detail" rule.
  - `validation.md` — 7 success criteria with required evidence,
    24 test cases, 12 edge cases, definition of done.
- Per-PR teaching artifacts: this explainer, the journey entry, the
  prs/README index row.

## Why this approach

The brainstorming earlier in the same session settled the major
decisions (Slice 1 = local→AssemblyAI→MD, diarization on by default,
per-utterance timestamps, `.env`-based key, `--budget free` errors out,
exit codes 0/2/3/4, tenacity retry per PLAN.md:631-636, general-purpose
YAML frontmatter, manual ~10s WAV runbook). Four polish questions
(filename convention, job-ID surfacing, soft cost cap, collision policy)
were asked + answered before any spec content was written, and all four
came back with the recommended option. The spec captures the result.

The spec deliberately **avoids** function signatures, dataclass field
names, and other low-level details. Those are decisions for the
implementer (a future Claude session, or a human contributor) to make
during the build, consistent with the SDD instruction "Do NOT
micromanage low-level implementation decisions the agent can figure out
on its own. ✅ Goals, Mission, Audience, Constraints. ❌ Variable names,
CSS classes, internal function signatures."

The "Why AssemblyAI is the first hosted provider" decision row in
`requirements.md` honors the new mission framing from PR #9 explicitly:
AssemblyAI is picked **on convenience** — specifically, the author has
~$60 of existing AssemblyAI credit they want to utilise first — not on
a claim that it is the most accurate or cheapest option. That distinction matters because the mission has accuracy as the
*primary* deciding factor for the long-term provider set, and the spec
should not silently override that ranking just because the MVP picks one
provider first.

## New Python idioms introduced

None — this PR is doc-only. The Python idioms used by the eventual
implementation (e.g. `Protocol`, `tempfile.mkdtemp` with context
manager, `tenacity.retry`, `frozen=True` dataclasses) will earn their
`python-notes.md` entries in the implementation PR, when there is real
code to cite.

## New AI/ML concepts introduced

None — same reason. Concepts that are *referenced* in the spec
(`provider abstraction`, `two-gate spend model`, `PreparedMedia`,
`RunWorkspace`) already live in the glossary from prior PRs. New
concepts that the implementation *introduces* (e.g. `tenacity` retry
patterns, polling for async-but-sync APIs) will earn their entries in
the implementation PR.

## What a reviewer should notice

- This PR is **doc-only and spec-only**. There is no `src/` change, no
  dependency change in `pyproject.toml`, and no test code. CI gates run
  only as a parity check.
- The spec triple is a **gate**, not implementation. Per
  `specs/2026-05-02-assemblyai-mvp-slice-1/plan.md` §9, implementation
  is a separate, future PR that begins only after the user explicitly
  approves this spec.
- `requirements.md` includes a "F1–F8 contracts: this slice's status"
  table that explicitly marks F3 (cache) and F6 (model preflight) as
  *deferred* for this slice and gives the reason. That table is the
  audit trail for the mission's note that the AssemblyAI MVP is a
  vertical-slice exception that "explicitly marks which F1–F8 contracts
  it implements vs defers."
- The "Why AssemblyAI is the first hosted provider" decision row makes
  clear that AssemblyAI was picked **on convenience** — specifically,
  the author has ~$60 of existing AssemblyAI credit to utilise first —
  not on accuracy or cost. Consistent with the mission's three-factor
  ranking. Reviewers worried about "but isn't this picking a paid
  provider as the *first* thing to ship?" should re-read that row.
- The user's `.env.example` already has the `ASSEMBLYAI_API_KEY=` slot
  at line 45 from prior infrastructure work. No `.env.example` change is
  needed for this slice.

## Interview angle

- **Story type:** workflow design / SDD discipline.
- **One-sentence hook:** "Writing the spec, the plan, and the validation
  triple *before* any code, so an implementer (human or AI) can build
  against a committed scope rather than guess from a chat transcript."
- **Pointer:** `interview-prep.md` — workflow design / agentic-engineering
  section (entry to be added when interview-prep is next refreshed,
  likely after the implementation PR lands).

## Further reading

- [`specs/2026-05-02-assemblyai-mvp-slice-1/requirements.md`](../../../specs/2026-05-02-assemblyai-mvp-slice-1/requirements.md)
- [`specs/2026-05-02-assemblyai-mvp-slice-1/plan.md`](../../../specs/2026-05-02-assemblyai-mvp-slice-1/plan.md)
- [`specs/2026-05-02-assemblyai-mvp-slice-1/validation.md`](../../../specs/2026-05-02-assemblyai-mvp-slice-1/validation.md)
- [`specs/mission.md`](../../../specs/mission.md) — mission framing this slice honors.
- [`docs/PLAN.md`](../../PLAN.md) §F1–F8, §Phase 5 — binding contracts the implementation has to honor.
- [`pr-008-adopt-sdd-constitution.md`](pr-008-adopt-sdd-constitution.md) — the SDD constitution this is the first feature loop under.
- [`pr-009-mission-provider-agnostic-framing.md`](pr-009-mission-provider-agnostic-framing.md) — the mission framing that makes accuracy primary, cost gating, convenience tiebreaker.
