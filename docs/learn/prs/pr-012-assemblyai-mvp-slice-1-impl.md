# PR #12 — Implementation: AssemblyAI MVP Slice 1

**Merged:** TBD  |  **Branch:** `impl/assemblyai-mvp-slice-1`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-12--implementation-assemblyai-mvp-slice-1`](../journey.md#pr-12--implementation-assemblyai-mvp-slice-1)

## The problem in one paragraph

PR #10 committed the spec triple for "local file → AssemblyAI → enriched
Markdown." This PR is the implementation against that spec. It is the
*first* feature loop the repo runs end-to-end under SDD, so it is also a
test of the workflow itself: did the spec capture enough that the
implementation could land without re-asking the architect, and were the
spec's exit-code / frontmatter / retry / polling contracts precise
enough that the test cases in `validation.md` could be written from the
spec alone? (Yes, with one design call surfaced explicitly: see "Why
this approach" below.)

## What changed (high level, not file-by-file)

Seven implementation commits land the slice in the order of `plan.md`'s
task groups, plus this teaching-artifacts commit:

1. **Deps + config.** `requests` and `tenacity` to runtime; `responses`
   and `types-requests` to dev. New `keep_temp` setting and an
   `assemblyai_configured` boundary helper that keeps the only
   `os.getenv("ASSEMBLYAI_API_KEY")` call inside `config.py`.
2. **F1/F2/F5/F8 minimal foundations.** `PreparedMedia` per F2,
   `LocalSource`, `RunWorkspace` per F5, ffmpeg-python audio extraction
   with explicit error mapping to exit code 4.
3. **F4 minimal two-gate budget.** Pure module: takes
   `key_configured` + `cost_usd` + injected `prompt`/`notify`
   callables; raises `BudgetError` on either gate; emits a louder
   warning above the $5 soft cap; honors `--yes` consistently.
4. **Provider layer.** `TranscriptionProvider` ABC + frozen result
   types; `AssemblyAIProvider` against the v2 REST API directly. The
   tenacity retry policy (3 attempts, exp backoff, retry only on
   429/502/503/504/timeout/connection error, never on permanent 4xx) is
   the heart of the cloud reliability story.
5. **Markdown formatter.** Stable-order YAML frontmatter matching the
   spec's contract exactly; body with `[mm:ss]` timestamps and
   `**Speaker A:**` prefixes both flippable via flags.
6. **CLI wiring.** Replaced the Phase-0 stub with the real pipeline.
   Exit-code matrix (0 / 2 / 3 / 4) is the contract every error path
   maps to. Removed legacy stub flags (`--quality`, `--no-cache`,
   `--summarize`) that belonged to phases that haven't landed yet;
   added `--no-speakers`, `--no-timestamps`, `--model`, `--max-wait`,
   `--keep-temp`.
7. **Tests + manual runbook.** 33 new unit tests across 6 files
   covering all 24 cases in `validation.md`, plus a manual
   `tests/manual/end_to_end.md` that costs ~$0.005 against a 10-second
   WAV and stays out of CI on purpose.
8. **This commit** (Task Group 8): pr-012 explainer, journey entry,
   prs/README index row, new glossary entry for `tenacity`, new
   python-notes entries for `typing.Protocol` and `tenacity.retry`,
   `specs/roadmap.md` Phase 5 status update.

## Why this approach

The most consequential implementation decision — flagged before the
provider layer was written — was **using `requests` + `tenacity`
directly instead of the official `assemblyai` SDK**. The spec's HTTP-
level test cases (`first 429 then 200 succeeds`, `three 429s fail after
retry exhaustion`, `401 fails immediately`) are assertions about the
exact retry policy. The SDK has its own retry logic that would compound
with ours, making those test cases ambiguous about which layer was
retrying which call. Going SDK-free meant adding `requests` to runtime
deps (already transitively present via `responses`) and removing
`assemblyai`. The implementation is ~150 lines of HTTP client; the
clarity of test ownership is worth that. Phase 5's full provider
abstraction can revisit the SDK choice when there are 3+ providers.

The second design pattern worth naming is **dependency injection for
testability**: the budget module takes `prompt` and `notify` callables
rather than importing `rich` or stdin; the AssemblyAI provider takes
`sleep` and `clock` callables so the polling-timeout test doesn't have
to wait 30 minutes. Java developers will recognize this as ordinary
constructor injection; Python codebases sometimes reach for monkey-
patching instead, which works but couples tests to implementation paths.
The injected-callable pattern keeps the unit boundary obvious.

## New Python idioms introduced

- [`typing.Protocol`](../python-notes.md#typing-protocol) — used for the
  formatter contract (`Formatter`); first time the repo uses Protocol-
  style structural typing.
- [`tenacity.retry` decorator](../python-notes.md#tenacity-retry) — the
  retry policy applied to every AssemblyAI HTTP call.

## New AI/ML concepts introduced

- [`tenacity`](../glossary.md#tenacity) — the retry library this slice
  introduces and that future Phase 5 cloud-provider work will reuse.

## What a reviewer should notice

- The PR is **large** (~1500 lines, 7 commits + this one) but each
  commit maps 1:1 to a `plan.md` task group, so reviewing commit-by-
  commit is feasible.
- The **F1–F8 status table** in `requirements.md` is the audit trail for
  the deferrals: F3 (cache) and F6 (model preflight) are explicitly
  documented as out of this slice. F4 (two-gate spend) is **minimal** —
  hardcoded around AssemblyAI; the provider-agnostic generalization
  stays in Phase 5.
- The **`os.environ` boundary** is honoured — exactly two reads exist
  (`config.py` and `providers/assemblyai.py`'s `_api_headers`), and the
  CLI uses `settings.assemblyai_configured` rather than reading env
  itself.
- The **`assemblyai` SDK is NOT in deps anymore** despite the spec
  having listed it. The decision is documented at the top of
  `providers/assemblyai.py` and in this explainer; reviewers concerned
  about vendor-SDK divergence should re-read that note.
- The **manual runbook** (`tests/manual/end_to_end.md`) has not been
  executed yet — verification evidence will be attached to the PR
  before merge. Real AssemblyAI calls deliberately stay out of CI.
- The **PR #7 missing learning artifact** (the merge-date backfill
  that shipped as `b798271`) is still not addressed. Pre-existing gap;
  not introduced by this PR; flagged again here for a future small
  follow-up.

## Interview angle

- **Story type:** end-to-end SDD execution / decision making under
  spec.
- **One-sentence hook:** "First feature loop under SDD: spec → impl →
  tests → real-API runbook, with a deliberate vendor-SDK rejection in
  favour of a thin `requests` + `tenacity` client because the spec's
  test cases were HTTP-level assertions that the SDK's own retry would
  have made ambiguous."
- **Pointer:** `interview-prep.md` — workflow design / agentic-
  engineering section (entry to be added when interview-prep is next
  refreshed).

## Further reading

- [`specs/2026-05-02-assemblyai-mvp-slice-1/requirements.md`](../../../specs/2026-05-02-assemblyai-mvp-slice-1/requirements.md)
- [`specs/2026-05-02-assemblyai-mvp-slice-1/plan.md`](../../../specs/2026-05-02-assemblyai-mvp-slice-1/plan.md)
- [`specs/2026-05-02-assemblyai-mvp-slice-1/validation.md`](../../../specs/2026-05-02-assemblyai-mvp-slice-1/validation.md)
- [`docs/PLAN.md`](../../PLAN.md) §F1–F8 + §Phase 5 — binding contracts.
- [`pr-008-adopt-sdd-constitution.md`](pr-008-adopt-sdd-constitution.md) — the SDD constitution this is the first feature loop under.
- [`pr-010-assemblyai-mvp-slice-1-spec.md`](pr-010-assemblyai-mvp-slice-1-spec.md) — the spec PR this PR implements.
- [`pr-011-plan-vad-and-transcription-boundary.md`](pr-011-plan-vad-and-transcription-boundary.md) — the PLAN tightening that lined up Phase 1's transcription boundary with the abstraction this slice's provider layer establishes.
