# PR #13 — Prevent vendor-API-shape regressions: SDD template + mock convention

**Merged:** TBD  |  **Branch:** `infra/prevent-vendor-api-shape-regressions`  |  **Codex review:** TBD
**Journey entry:** [`../journey.md#pr-13--prevent-vendor-api-shape-regressions-sdd-template--mock-convention`](../journey.md#pr-13--prevent-vendor-api-shape-regressions-sdd-template--mock-convention)

## The problem in one paragraph

PR #12's first end-to-end run against a real audio source failed three
times in a row, each time exposing a defect that 41 unit tests had
missed: a `pydantic-settings`/`monkeypatch.setenv` mismatch that masked
the `.env` loading bug, a deprecated AssemblyAI request field name
(`speech_model` -> `speech_models`), and retired model identifiers
(`best`/`nano` -> `universal-3-pro`/`universal-2`). The defects split
into two classes: **#2 and #3 are vendor API drift** with a shared
root cause — the implementation paraphrased shape information from
training data instead of copying from a known-working source — while
**#1 is a test-environment bypass** (a different class with its own
structural fix in PR #12 itself, the `load_dotenv()` call). Defect #2
also had a separate hiding mechanism: the `responses` mocks matched
URL+method only and never the request body shape. **PR #13 closes the
vendor-shape class** (defects #2 and #3); defect #1 was already fixed
in PR #12. The combination prevents the same class of bug from
recurring silently.

## What changed (high level)

Three coordinated additions, no code paths touched:

1. **`specs/REQUIREMENTS_TEMPLATE.md`** (new) — the canonical starting
   shape for `specs/YYYY-MM-DD-<feature>/requirements.md`. The
   load-bearing addition is the **`## Reference calls (verbatim)`**
   section: any feature integrating with a third-party API must paste
   working request and response shapes there, with a docs URL and
   retrieval date. The implementer copies from this section into code
   and tests. *Never paraphrase from memory or training data* is the
   explicit rule.
2. **`CLAUDE.md` guardrails** (two new bullets):
   - Vendor API calls must reference a verbatim working call (or a
     fresh ctx7 fetch with retrieval date). Names PR #12 as the reason.
   - HTTP mocks must use `responses.matchers.json_params_matcher` (or
     equivalent) to assert request body shape, not just URL+method.
     Names PR #12's regression test as the exemplar.
3. **`specs/README.md`** — one-line pointer to the new template under
   the per-feature-specs section.

## Why this approach

The user posed the question after PR #12: "how can we avoid the issues
you faced in the future? using ctx7 might help?" The honest answer
required separating the three defects by class:

- **#2 and #3 (vendor API drift)** would have been caught by ctx7 *if*
  invoked at write time. They would also have been caught by simply
  copying the user's working curl, which already had the correct
  shape (`speech_models: ["universal-3-pro"]`). The user's curl was
  the cheapest available defence and was discarded by paraphrase. So
  the structural fix is the spec template: **make the working call
  the canonical source of truth, and make copying from it a written
  rule.**
- **#1 (`.env` loading bypass)** is a different class — `monkeypatch.setenv`
  populates `os.environ` directly and bypasses the `.env`-loading
  code path entirely, so unit tests passed even though the
  user-facing onboarding workflow was broken. The fix for that lives
  in PR #12 itself (call `load_dotenv()` at config import) plus the
  manual real-API runbook (which already exists). PR #13 doesn't try
  to address it again — the runbook caught it once; the load_dotenv
  call now prevents it from recurring.
- **The mock-fidelity gap** (silent in #2 because the `responses`
  mocks only matched URL+method) is the third defence. PR #12 added
  one body-shape matcher test as a regression check; PR #13 promotes
  body-shape matching from "the new convention" to "a CLAUDE.md rule"
  so the next provider PR (Phase 5: Deepgram, OpenAI Whisper, Hugging
  Face) doesn't replicate the gap.

ctx7 is mentioned as the *fallback* path in the template — for
features where no working call exists yet (new vendor, exploratory
work). It is intentionally not made a hard dependency: tooling that
requires a separate setup step is fragile in practice, while a spec
template section is enforced by the spec itself with no setup cost.
The combination of the three defences (template section + body-shape
matchers + ctx7 fallback) catches the same class of bug at three
different stages: spec review (will the implementer have a working
call to copy?), unit-test write-time (does the request body shape
match what the test asserts?), and pre-implementation docs research
(when no working call exists, are we reading the live API contract or
guessing from training data?).

## What a reviewer should notice

- This PR is **doc-only**: no code, no tests, no dependency changes.
  CI gates (pytest, ruff, mypy) are green by default; verifying them
  is just a sanity check that nothing in the doc changes broke an
  unrelated parser.
- The template is **opinionated about Reference calls** and
  intentionally lighter on other sections — the goal is not to
  template the whole spec, only to lock in the section that addresses
  the PR #12 incident class.
- The CLAUDE.md guardrails reference PR #12 by number rather than
  inlining the defect details. The journey + the PR #12 explainer are
  the long-form home for that story; the guardrail just needs to be
  enforceable.
- ctx7 is **not** added as a hard repo dependency. Setup is user-
  driven (one-time `npx ctx7 setup`); the spec template references
  it as the fallback path only. Fragility argument: a guardrail that
  requires a separate MCP server install on every contributor's
  machine is harder to enforce than a guardrail that requires copying
  text into a doc.

## Interview angle

- **Story type:** post-incident structural fix; defence-in-depth at
  three different lifecycle stages.
- **One-sentence hook:** "After three real-API defects in one run,
  diagnosed two as vendor drift and one as test bypass, then added
  three layered defences for the vendor-drift class: a verbatim-call
  section in the SDD spec template, a body-shape mock guardrail, and a
  ctx7 fallback for new vendors — each catching the same class of bug
  at a different stage (spec review, unit-test write-time, docs
  research)."

## Further reading

- PR #12 ([`pr-012-assemblyai-mvp-slice-1-impl.md`](pr-012-assemblyai-mvp-slice-1-impl.md), available on `main` once PR #12 merges) — the incident this PR is the structural follow-up to; "What the manual real-API run caught" section captures the three defects.
- [`../../../specs/REQUIREMENTS_TEMPLATE.md`](../../../specs/REQUIREMENTS_TEMPLATE.md) — the new template.
- [`../../../CLAUDE.md`](../../../CLAUDE.md) — the two new guardrail bullets.
