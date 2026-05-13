# Journey

> Running narrative of what was built in SSM-Transcriber and *why*, written in
> teaching register. **Newest first.** Each PR gets one entry; update the
> `Merged:` line after merge. This is
> the companion to the commit history — `git log` tells you *what*, this file
> tells you *why it mattered and what you should take away from it*.
>
> If you're reading this for the first time, scroll to the bottom and read
> forward. If you're catching up, read top-down.

---

## PR #31 — Implementation: YouTube Source (Captions Passthrough)

**Merged:** TBD  |  **Branch:** `feat/youtube-captions-source-impl`
**Explainer:** [`prs/pr-031-youtube-captions-source-impl.md`](prs/pr-031-youtube-captions-source-impl.md)

PR #31 ships the captions-only YouTube source the spec PR #30 designed.
The captions path is **$0 by construction** — `youtube-transcript-api`
fetches existing manual or auto-generated captions, oembed resolves
the video title via a fail-soft public GET, and the CLI branches on
`isinstance(media, PreparedTranscript)` *before* the budget router
fires. No audio download, no paid ASR call. The architectural change
is the `PreparedSource` Protocol + new `PreparedTranscript` sibling
dataclass — F2's third source-mode lands as a clean refactor rather
than a third additive extension to `PreparedMedia` (whose name was
about to lie). The provider abstraction stays typed on the concrete
`PreparedMedia`, so mypy enforces "captions never reaches a provider"
at compile time. Videos without captions exit 2 with a documented
message that points at issue #21 and offers a copy-paste `yt-dlp` +
Phase 1 local-ASR workaround. 51 new tests; 261 total project-wide;
ruff + mypy clean.

---

## PR #30 — Feature spec: YouTube Source (Captions Passthrough)

**Merged:** 2026-05-12  |  **Branch:** `feature/youtube-captions-source-spec`
**Explainer:** [`prs/pr-030-youtube-captions-source-spec.md`](prs/pr-030-youtube-captions-source-spec.md)

PR #30 committed the spec triple for Phase 2 Slice 1 (issue #20):
requirements / plan / validation for a captions-only YouTube source.
Seven design decisions settled in the brainstorm — caption types
(manual + auto, exclude auto-translated), track-selection policy
(original-language-first, ignore `--language`), source contract
(`PreparedSource` Protocol + new `PreparedTranscript` sibling),
frontmatter (`provider`/Optional `model`/Optional `job_id` on
`TranscriptResult`; additive `caption_type` field on captions
frontmatter), library reliability (version pin, no cache, narrow
retry whitelist, typed error matrix), budget gate (bypassed
entirely), no-captions error wording (points at issue #21 with a
yt-dlp workaround). Codex review flagged two P2 internal
contradictions both fixed inline before merge. The single
architectural decision worth retelling: the F2 contract had been
extended additively twice (Drive added `remote_url`); a third
extension would have made the "media" name dishonest, so Slice 1
refactors to Protocol + sibling instead.

---

## PR #19 — Drive Upload: transcript → Google Drive

**Merged:** TBD  |  **Branch:** `feat/drive-upload`
**Explainer:** [`prs/pr-019-drive-upload.md`](prs/pr-019-drive-upload.md)

PR #19 adds Google Drive as an upload destination for transcripts. The
`--upload-to-drive` flag on `transcribe` and a standalone `upload` subcommand
both route through a thin `OutputDestination` Protocol, consistent with the
`TranscriptionProvider` pattern. Auth is a one-time `auth google-drive`
subcommand that persists a refresh token with 0600 permissions; the Drive
`drive.file` scope limits the app to files it creates. The local `.md` is
always written before upload is attempted — transcript loss on failure is
impossible by construction.

---

## PR #18 — Fix AssemblyAI rate constant + factor in diarization

**Merged:** TBD  |  **Branch:** `fix/assemblyai-rate-constant`
**Explainer:** [`prs/pr-018-assemblyai-rate-constant-fix.md`](prs/pr-018-assemblyai-rate-constant-fix.md)

PR #18 fixes a Slice 1 (PR #12) bug that PR #17's manual runbook
caught: `ASSEMBLYAI_RATE_PER_MINUTE_USD = 0.009` was 2.35x too high.
Empirical AssemblyAI dashboard data across two independent days
showed the actual rate is **$0.0035/min for Universal-3 Pro +
$0.000333/min for Speaker Diarization** — split into two constants
because diarization is optional (`--no-speakers` flips it off) and
AssemblyAI bills it separately. `estimate_assemblyai_cost` gains a
`diarize: bool = True` keyword so both `--speakers` and
`--no-speakers` flows quote accurately. Test
`test_estimate_cost_matches_real_pr17_run` locks the rate against
the empirical PR #17 figure ($0.2415 for 63 min, diarization on); a
future rate change will fail this assertion and force re-verification
against fresh dashboard data.

Slice 2 (Drive) sources are unaffected — they use the `cost_summary`
override and skip the per-minute estimate entirely, structurally
insulating themselves from this bug class. The "skip pre-estimate
for URL-passthrough sources" decision (PR #15 brainstorm #4) thus
proved more valuable than its original "we have no local duration"
rationale: it also dodged a wrong-constant landmine the local-file
path stepped on.

The structural lesson the manual runbook surfaced: 12 weeks of unit
tests missed this because the bug was in a constant, not a code
path. Tests of cost math against the constant still passed; only
runtime comparison against authoritative billing data caught it.
Manual runbooks aren't ceremony — they're the only place wire-rate
truths land.

---

## PR #17 — Implementation: Drive Source (URL passthrough)

**Merged:** TBD  |  **Branch:** `feat/drive-source-impl`
**Explainer:** [`prs/pr-017-drive-source-passthrough-impl.md`](prs/pr-017-drive-source-passthrough-impl.md)

PR #17 is the implementation against the spec PR #15 committed and the
execution plan PR #16 ratified (after two review rounds — one inline
during plan-writing and one via parallel `pr-review-toolkit` agents
that flagged 8 safety-critical findings). The slice ships in 8 TDD
commits that each map 1:1 to a plan task group: F2 contract extension
+ `SourceInputError`, Drive URL parser, `DriveSource.prepare` +
`LocalSource.prepare(title=...)`, `resolve_source` dispatcher with
reject-not-swallow, provider `audio_url` passthrough branch, `--title`
sanitization helpers, formatter handling `local_path=None`, and the
CLI integration that threads everything together.

The single biggest implementation-phase decision was C1 — how to
thread the canonical 16 kHz mono WAV path back into `media` after
`extract_audio` runs. Without `dataclasses.replace(media,
local_path=wav_path)`, the provider would silently upload the
original `.mp4` instead of the workspace-extracted WAV. AssemblyAI
accepts any audio container, so the regression would ship through
135 unit tests undetected — exactly the kind of "tests pass but
contract is broken" finding that justifies the plan-PR-sandwich
cadence the user adopted after PR #12.

The Drive URL passthrough adds zero new dependencies and saves the
download+upload round-trip on hour-long files. OAuth + private files
remain explicitly deferred to Slice 3.

Phase 4 status moves from `pending` to `partial — public-link
passthrough only (Slice 2: PR #16 spec + plan, this PR's
implementation). OAuth + private files deferred to Slice 3.`

---

## PR #16 — Execution plan: Drive Source (URL passthrough)

**Merged:** 2026-05-04  |  **Branch:** `impl/drive-source-passthrough`
**Explainer:** none — doc-only PR, see the plan triple itself.

PR #16 is the execution plan that bridged spec (PR #15) and
implementation (PR #17). The PR was deliberately kept doc-only so
two review rounds could fire against the proposed code snippets
*before* any runtime code landed: an inline review caught 10 plan-
level findings (all 10 applied), then a formal `pr-review-toolkit`
parallel review surfaced 14 more — 1 critical, 8 important, 5
suggestions. The 8 safety-critical from the formal round (1 critical
+ 7 important) were applied to the plan; the remaining 6 (1 important
+ 5 suggestions) were deferred as type-design refactors and polish
warranting their own follow-up review. Total applied across both
rounds: 18 findings, including the WAV-vs-source upload regression
(C1) that would have shipped silently through 135 unit tests had the
formal review not fired. This PR established the plan-PR-sandwich
cadence (spec → plan → impl) the repo will use for future feature
loops.

---

## PR #15 — Feature spec: Drive Source (URL passthrough)

**Merged:** TBD  |  **Branch:** `feature/drive-source-passthrough-spec`
**Explainer:** [`prs/pr-015-drive-source-passthrough-spec.md`](prs/pr-015-drive-source-passthrough-spec.md)

PR #15 is the spec for the second source — Google Drive videos the
user has already shared as anyone-with-link. The straight-line answer
from PLAN.md's Phase 4 was OAuth + `google-api-python-client`
download, but the brainstorm surfaced a working `curl` early on that
points at a fundamentally cheaper path: pass the public Drive
download URL straight to AssemblyAI's `audio_url` field and let
AssemblyAI fetch it server-to-server. No OAuth, no download, no
upload, ~5–10× faster on hour-long files.

The four user-facing decisions the brainstorm settled (auth model,
URL forms accepted, frontmatter title source, cost pre-estimate
strategy) all converged on "smallest thing that ships value today."
OAuth and Drive folder traversal are deferred to a future Slice 3,
explicitly documented rather than implicitly skipped. The single
architectural change is additive: `PreparedMedia.local_path` becomes
`Path | None` and a new `remote_url: str | None` field lands.
Provider branches once on `if media.remote_url`. Polling, retry,
formatter all reuse Slice 1's plumbing unchanged.

The single most interesting thing about this PR for the SDD story:
**it's the first feature spec to fill in PR #13's
`## Reference calls (verbatim)` section.** PR #13's premise was
"wrong vendor API shape because the implementation paraphrased
rather than copied"; this spec proves the prevention pattern is
followable in practice — the user's actual working `curl` is pasted
at the top of `requirements.md` so the implementer copies from it
byte-for-byte instead of paraphrasing from training data. The
template + this dogfood test together close the loop the PR-12
defects opened.

The takeaway: cheapest-acceptable-architecture decisions become much
easier to make under SDD when the brainstorm surfaces a working
example early. The user's working curl wasn't a stray data point —
it was the architectural argument. The spec just made that argument
the documented record.

---

## PR #14 — Housekeeping: merge-date backfills, roadmap Phase 5 update, PR #7 explainer

**Merged:** 2026-05-04  |  **Branch:** `chore/housekeeping-merged-dates-pr7-explainer`
**Explainer:** [`prs/pr-014-housekeeping-merge-dates-roadmap-pr7-explainer.md`](prs/pr-014-housekeeping-merge-dates-roadmap-pr7-explainer.md)

PR #14 is the rare bundling exception — three small follow-ups too
small to ship individually, packaged into one housekeeping PR. The
contents: backfill `Merged: TBD` → actual dates on PR #12 and PR #13
journey entries (extending the convention PR #7 itself established
for PR #6); update `specs/roadmap.md` Phase 5 status to mention PR
#13's structural defences alongside PR #12's implementation; finally
write the long-pending PR #7 explainer (the gap had been flagged
across PRs #6, #8, #10, #12, and #13).

The interesting bit isn't the changes themselves but the bundling
decision. The default is one PR per concern; this PR has three.
Worth doing only when each concern would otherwise be ceremony-heavy
and the bundle has a unifying frame (here: "housekeeping that
accumulated since PR #13 merged"). The PR description was honest
about the bundling — it called out exactly three items and
explicitly documented one *deliberate* exclusion (Phase 1
Foundations status update was flagged as a follow-up rather than
expanded into).

The takeaway: convention adherence isn't reflexive. The "every PR
from #3 onward drafted before opening" rule has now been broken
twice — once by PR #7 (a 2-line mechanical change with no
brainstorm to draft from) and again by PR #14 itself (whose
explainer was missed at merge and backfilled in PR #15's review
cycle). Both backfills are themselves the documented pattern, not
silent exceptions. The convention text in `prs/README.md` will keep
catching up.

---

## PR #13 — Prevent vendor-API-shape regressions: SDD template + mock convention

**Merged:** 2026-05-04  |  **Branch:** `infra/prevent-vendor-api-shape-regressions`
**Explainer:** [`prs/pr-013-prevent-vendor-api-shape-regressions.md`](prs/pr-013-prevent-vendor-api-shape-regressions.md)

PR #13 is the structural follow-up to PR #12. The first end-to-end run
in PR #12 surfaced three defects in a single attempt:
`monkeypatch.setenv` masked the `.env` loading bug, AssemblyAI had
deprecated the singular `speech_model` field for plural `speech_models`,
and `best`/`nano` were retired in favour of `universal-3-pro` /
`universal-2`. The fixes for each landed in PR #12. The defects split
into two classes: the field-name and model-name defects (#2, #3) are
*vendor API drift* — the implementation paraphrased shape information
from training data instead of copying from a known-working source. The
`.env` defect (#1) is a different class — a test-environment bypass
where `monkeypatch.setenv` populated `os.environ` directly without ever
exercising the `.env`-loading path. This PR closes the **vendor-shape
class** (#2, #3) by codifying three layered defences:

1. A new `specs/REQUIREMENTS_TEMPLATE.md` whose **`## Reference calls
   (verbatim)`** section is required for any feature integrating with a
   third-party API. The user's own working call goes here verbatim, with
   a docs URL and retrieval date. The implementer copies from this
   section into code and tests; paraphrase is explicitly disallowed.
2. A CLAUDE.md guardrail mandating body-shape matchers for HTTP mocks
   (`responses.matchers.json_params_matcher`), with PR #12's
   regression test as the named exemplar. URL+method-only matching is
   how PR #12's wrong-field-name defect slipped past 41 unit tests.
3. A second CLAUDE.md guardrail mandating that vendor API calls must
   reference a verbatim source — either the spec's Reference calls
   section or a fresh ctx7 docs fetch with retrieval date — never
   paraphrase from memory or training data. PR #12 named the cost.

ctx7 is the *fallback*, not the primary defence. A guardrail that
requires a separate MCP server install on every contributor's machine
is harder to enforce than a guardrail that requires copying text into a
doc. ctx7 fills the gap when no working call exists yet (new vendor,
exploratory work). The combination catches the same class of bug at
three different stages: spec review, unit-test write-time, and pre-
implementation docs research.

The takeaway: the manual real-API runbook in `validation.md` is a
*detection* gate (it caught the defects), but it doesn't prevent them.
PR #13 is the *prevention* layer — structural, doc-only, no code touched.
That separation is deliberate: detection and prevention are different
problems and want different tools.

---

## PR #12 — Implementation: AssemblyAI MVP Slice 1

**Merged:** 2026-05-03  |  **Branch:** `impl/assemblyai-mvp-slice-1`
**Explainer:** [`prs/pr-012-assemblyai-mvp-slice-1-impl.md`](prs/pr-012-assemblyai-mvp-slice-1-impl.md)

PR #12 is the first end-to-end feature loop the repo runs under SDD,
and the first PR that ships running code instead of constitution or
spec. The implementation lands the AssemblyAI MVP Slice 1 spec from
PR #10 — local file → ffmpeg → AssemblyAI v2 REST → enriched Markdown
with a stable YAML frontmatter — across seven implementation commits
that map one-to-one to the spec's nine task groups, plus a teaching-
artifacts commit. Every test case in `validation.md` (24 of them) has a
matching unit test; the one real-API verification step lives in a
manual runbook (`tests/manual/end_to_end.md`) that costs ~$0.005 per
run and stays out of CI on purpose.

The single most valuable lesson from this PR landed *after* the 41-test
unit suite went green: the first end-to-end run against a 67-min real
audio source failed three times in a row, each surfacing a real defect
the unit tests had missed (`.env` loading bypassed by `monkeypatch.setenv`,
deprecated AssemblyAI request field, retired model name). Fix commits
`d5eb072`, `ea3d852`, `46ccaa1` patched all three; the fourth attempt
produced the expected diarized markdown. The unifying pattern was
**"unit tests passed but real API failed,"** but the *root causes split
into two classes*: defects #2 and #3 were vendor API drift (no mock
could catch the deprecated field name or the retired model identifier
at unit-test time, because both describe the live wire contract);
defect #1 was a test-environment bypass (`monkeypatch.setenv` populates
`os.environ` directly and never exercises the `.env`-loading path that
production actually uses). Defect #2 had a separate, additional gap
that hid it locally — the `responses` mocks matched URL+method only,
never the request body shape — so the body-shape regression test added
with the fix double-protects against future field-name regressions.
The manual real-API runbook in `validation.md` was vindicated as a
*hard gate* rather than a nice-to-have: that's exactly what it exists
to catch. (PR #13 is the structural prevention layer for the vendor-
drift class; the test-bypass class is fixed structurally by the
`load_dotenv` call landed here.)

The design call most worth reading is the **rejection of the official
`assemblyai` SDK** in favour of a thin `requests` + `tenacity` client.
The spec's test cases — "first 429 then 200 succeeds via retry",
"three 429s fail after exhaustion", "401 fails immediately with no
retry" — are assertions about the exact retry policy. The SDK has its
own retry layer, which would compound with ours and make those test
cases ambiguous about which layer was actually retrying. Going
SDK-free traded ~150 lines of HTTP client for unambiguous test
ownership. Phase 5's full provider abstraction (multi-provider
registry) can revisit the SDK question when there are 3+ providers.

The second pattern worth naming is **dependency injection for
testability**: the budget module takes `prompt` and `notify` callables
rather than importing `rich` or stdin; the AssemblyAI provider takes
`sleep` and `clock` callables so the polling-timeout test doesn't have
to wait 30 minutes. Java developers will recognize this as ordinary
constructor injection; Python codebases sometimes reach for monkey-
patching instead, which works but couples tests to implementation
paths. The injected-callable pattern keeps the unit boundary obvious
and the tests fast.

The takeaway from this loop: **SDD scales when the spec is precise
enough that the implementation can ship without re-asking the
architect, but not so prescriptive that the implementer can't make
real engineering calls.** The SDK-vs-raw-HTTP decision is the kind of
choice the spec correctly *did not* make for the implementer; the spec
specified the behaviour (retry exactly these codes exactly this many
times) and trusted the implementer to pick the cleanest way to honour
it. That separation is what made the test cases verifiable rather than
loose.

New Python idioms:
[`typing.Protocol`](python-notes.md#typing-protocol),
[`tenacity.retry` decorator](python-notes.md#tenacity-retry).
New tooling concept:
[`tenacity`](glossary.md#tenacity).

---

## PR #11 — PLAN: tighten VAD framing and Phase 1 transcription boundary

**Merged:** TBD  |  **Branch:** `docs/plan-vad-and-transcription-boundary`
**Explainer:** [`prs/pr-011-plan-vad-and-transcription-boundary.md`](prs/pr-011-plan-vad-and-transcription-boundary.md)

PR #11 is a tiny doc-only PR — three single-line edits to
`docs/PLAN.md` — but it closes two pieces of internal drift that would
have cost real time later. The first edit removes the last
"strip silence with VAD before upload" reference from the cost table.
That framing contradicted the F-cost-section principle "VAD is a sidecar
only; do not strip canonical audio before transcription" (also stated in
`CLAUDE.md`). It would also have broken sentence-level timestamp
alignment with the original media if anyone had implemented against the
older cost-table wording. The new wording — "Optimize VAD at the
transcription engine level (preserve timestamps)" — matches what every
other doc in the repo already says.

The second edit adds an explicit "define a minimal transcription
boundary/interface here early" note to the Phase 1 transcriber file
description. Without this, Phase 1's `faster-whisper` wrapper would have
been wired directly into source code, and every later provider PR would
have had to refactor those call sites. With this, the boundary lands
once in Phase 1, and the in-flight AssemblyAI Slice 1 implementation
(PR #10 spec) plus eventual Phase 5 generalization become *additive*
rather than rewrites.

The takeaway: doc PRs are not just tidying. The PLAN file is what every
AI tool reads before writing implementation code; a stale line there
becomes a stale line in the next implementation PR. PR #6 made this
case for naming drift; PR #9 made it for the project-identity framing;
PR #11 makes it for principle-vs-table consistency. Same lesson, smaller
scope each time — which is the point.

This PR follows the same pattern PR #9 used: constitution-level edit,
own branch, kept separate from the in-flight feature work
(`impl/assemblyai-mvp-slice-1` is on its own branch and not affected by
this).

---

## PR #10 — Feature spec: AssemblyAI MVP Slice 1

**Merged:** TBD  |  **Branch:** `feature/assemblyai-mvp-slice-1`
**Explainer:** [`prs/pr-010-assemblyai-mvp-slice-1-spec.md`](prs/pr-010-assemblyai-mvp-slice-1-spec.md)

PR #10 is the first real test of SDD on this repo: the constitution
landed (PR #8), the mission was reframed (PR #9), and now the first
feature loop produces a spec triple — `requirements.md`, `plan.md`,
`validation.md` — *before* any code. The slice itself is small in scope
(local file → AssemblyAI → Markdown) but load-bearing: it validates the
whole paid-provider plumbing (two-gate spend, tenacity retry, polling,
atomic write, frontmatter) on a 30-second WAV before the Drive source
loop adds OAuth on top.

The interesting design pressure was *not* the technical decisions — the
brainstorming earlier in the same session settled those (diarization on
by default, per-utterance timestamps, `.env`-based key, soft $5 cost cap,
suffix-increment collision policy). The pressure was on what the spec
should and should *not* contain. SDD says "Goals, Mission, Audience,
Constraints — yes; variable names, function signatures — no." So the
spec deliberately stops at task groups (e.g. "implement the markdown
formatter") and trusts the implementer to decide internal function
signatures during the build. That's harder than it sounds: the temptation
to over-specify in advance is real.

The "Why AssemblyAI is the first hosted provider" decision row makes the
spec self-explanatory under the new mission framing: AssemblyAI is picked
on **convenience** (existing credit + working SDK + familiar API), not on
a claim that it is the most accurate or cheapest option. The mission
ranks accuracy as the primary deciding factor for the long-term provider
set; the spec records that the MVP's choice does not silently override
that ranking.

The takeaway: feature specs are not a replacement for chat brainstorms;
they are the *artifact* of the brainstorm, committed before
implementation so that drift between the conversation and the code is a
review-blocker, not an after-the-fact discovery.

---

## PR #9 — Mission: provider-agnostic framing with default-cheap

**Merged:** TBD  |  **Branch:** `docs/mission-provider-agnostic-framing`
**Explainer:** [`prs/pr-009-mission-provider-agnostic-framing.md`](prs/pr-009-mission-provider-agnostic-framing.md)

PR #9 is a small but real repositioning of the project identity. The
mission statement that landed in PR #8 led with "local-first," which was
inherited from older repo language and was doing two jobs at once: stating
a cost philosophy (default to $0) and stating a project identity (local is
the canonical path, cloud is the exception). Both were defensible until the
author surfaced a concrete future goal — head-to-head accuracy and cost
comparison across providers — that fits awkwardly under a "local-first
always" identity.

This PR keeps the cost protection but drops the asymmetric framing. Local
and hosted providers are now described as first-class peers in
`specs/mission.md`; the default budget is still `free` so casual use still
costs `$0`; the two-gate spend protection (configured key + explicit
`--budget low|best` + cost confirmation) is preserved verbatim. The mission
now ranks three deciding factors: **accuracy is primary**, **cost is the
gating constraint**, and **convenience is a legitimate tiebreaker** —
"cheapest" alone is not a sound reason to pick a transcription provider;
cost determines whether a paid option is available at all, not which paid
option to pick when several pass the budget; and a real user can
reasonably reach for a provider they already have wired up rather than
re-optimize from scratch every job. A new "in scope" bullet records that
head-to-head provider evaluation (accuracy first, then cost) is a stated
future direction and is intended to drive future provider and default
choices; the MVP's AssemblyAI choice is provisional pending those
evaluations, with accuracy as the primary tiebreaker.

The takeaway: a project's elevator pitch is not just marketing — it
constrains what feels in-scope vs out-of-scope to the next implementer (AI
or human). When the elevator pitch and the actual long-term vision diverge,
fix the pitch early. Doing it later is harder because more downstream docs
will have inherited the older framing.

There is a remaining inconsistency in `docs/PLAN.md` (a "Local-first,
always" header under the Cost Optimization Strategy section) — it reads as
a *strategy principle* rather than an identity claim, so it does not
contradict the new mission, but it is the next sentence worth revisiting if
PLAN.md is edited for any other reason. Flagged in the explainer, not
addressed in this PR.

---

## PR #8 — Adopt SDD: bootstrap project constitution under `specs/`

**Merged:** TBD  |  **Branch:** `sdd/constitution-bootstrap`
**Explainer:** [`prs/pr-008-adopt-sdd-constitution.md`](prs/pr-008-adopt-sdd-constitution.md)

PR #8 is the repo crossing a workflow threshold. After PR #6 stabilized the
docs and removed drift, the natural next question was: when an AI tool
opens this repo cold, where does it start? Five well-edited files (README,
PLAN, learn/, CLAUDE.md, ai/) are still five files. The author adopted
Spec-Driven Development (SDD) — write the spec first, implement against
it — and wanted a `specs/` directory holding mission, tech-stack, and
roadmap as the project constitution, then per-feature folders for each
loop.

The brownfield trap was sharp: this repo already has effective
mission/stack/roadmap content. Naively duplicating it into `specs/` would
re-create the exact drift PR #6 had just finished cleaning up. So the
approach this PR settles on is the **lightweight bridge**: `specs/` files
are small (~250 lines total), summarize the canonical sources for an
agent reading the constitution alone, and link out for detail. Roadmap
headings are *verbatim* from `docs/PLAN.md` so a rename is a one-PR fix
instead of a drift event. F1–F8 contract names are inlined; bodies stay
in PLAN.md.

The takeaway: adopting a new workflow on a brownfield repo isn't about
recreating the project — it's about adding the *missing layer* without
touching the layers that already work. The bridge file pattern is reusable
any time you want a stable agent-facing surface that summarizes content
living somewhere else.

AI workflow concepts introduced:
[`Spec-driven development`](glossary.md#spec-driven-development).

---

## PR #7 — Backfill PR #6 merge date

**Merged:** 2026-05-01  |  **Branch:** `chore/pr-6-merged-date-backfill`
**Explainer:** [`prs/pr-007-backfill-pr-6-merge-date.md`](prs/pr-007-backfill-pr-6-merge-date.md)

PR #7 is the smallest possible follow-up to PR #6 and exists for one
reason: PR #6 introduced the convention of backfilling `Merged: TBD`
placeholders with the actual merge date once a PR lands, but it
couldn't apply that convention to itself (the date isn't known until
after the merge). PR #7 is the 2-line backfill that applied the same
pattern to PR #6's own journey entry and explainer header.

The takeaway is small but real: post-merge backfills are the
*documented* pattern, not a missed step at merge time. They land in a
follow-up PR exactly like this one. (This explainer was drafted
retroactively as part of the housekeeping bundle after PR #13 — the
learning-artifact gap had been flagged across PRs #6, #8, #10, #12,
and #13.)

---

## PR #6 — Roadmap naming cleanup and hosted-provider strategy

**Merged:** 2026-05-01  |  **Branch:** `codex/docs-stale-naming-cleanup`
**Explainer:** [`prs/pr-006-roadmap-naming-and-hosted-provider-strategy.md`](prs/pr-006-roadmap-naming-and-hosted-provider-strategy.md)

PR #6 is a reminder that doc drift can be an architecture bug, not just a
copy-editing bug. By the time this branch opened, the repo had already
decided that the user-facing CLI stays `ssm-transcriber` while Python imports
stay `transcriber`, that `docs/PLAN.md` owns contracts while `docs/learn/`
owns teaching rules, and that Phase 5 was starting to outgrow a simple
`cost_per_minute` scalar. But several docs still described the older state.

The risk was subtle but real: this repo is intentionally built for multiple
AI tools, and those tools read the docs as if they were implementation
constraints. If one file says the naming split is still undecided, another
says the provider API is definitely `cost_per_minute`, and a third starts
talking about Hugging Face without spelling out that it is explicit-only and
not a default routing candidate, the next implementation PR can follow the
wrong map while still looking "consistent" locally.

So this PR does three cleanup jobs in one pass. It removes stale naming and
CLI references, rewrites the provider story around a shared transcription
contract plus a richer estimation hook, and frames Hugging Face as a later
experimental hosted-provider option that must not bypass the repo's `$0`
default or two-gate spend model. It also updates the learning artifacts so
the explainer index, journey, and Python notes all tell the same story.

The takeaway: when your docs are load-bearing inputs to humans *and* coding
agents, keeping them in sync is part of the design work. Treat a stale doc
the same way you'd treat a stale interface comment that future code will
compile against.

Architecture concepts clarified:
[`provider abstraction`](glossary.md#provider-abstraction),
[`two-gate spend model`](glossary.md#two-gate-spend-model).
Python note updated:
[`@property`](python-notes.md#property).

---

## PR #5 — AI operator guide + workflow commands

**Merged:** 2026-04-13  |  **Branch:** `infra/agent-skills-commands`
**Explainer:** [`prs/pr-005-ai-operator-guide-workflow-commands.md`](prs/pr-005-ai-operator-guide-workflow-commands.md)

PR #5 is the repo admitting that "five context files in lockstep" was the
right starting move and the wrong long-term maintenance model. It worked for
Phase 0 and PR #3 because the rule set was still small. But as the repo added
teaching-register rules, F1–F8 contracts, and tool-specific extensions, every
workflow tweak wanted to touch half the root.

The fix here is not "one giant AI doc." That would only move the drift problem
to a different file and make every tool rediscover more prose than it needs on
the first turn. Instead this PR adds an operator-guide layer in `docs/ai/` and
a small set of runbooks for workflow-heavy tasks. `docs/PLAN.md` still owns
technical contracts; `docs/learn/README.md` still owns living-doc rules.

The second design choice is that workflow commands have to earn their keep.
`/build` and `/test` look neat, but they do not save enough repo-specific
thought to justify another maintained file. The commands that remain
(`review`, `ship`, `new-pr`, `phase-check`) all exist because they package a
real checklist, evidence table, or narrative workflow.

The takeaway: centralize source docs, not every sentence. Keep root tool files
short but still self-sufficient, and move multi-step reasoning into runbooks
that tools can load on demand.

AI workflow concepts introduced:
[`AI context file`](glossary.md#ai-context-file),
[`runbook`](glossary.md#runbook),
[`slash command`](glossary.md#slash-command).
Vibe-coding lessons:
[`Multi-tool context strategy`](vibe-coding-notes.md#multi-tool-context-strategy),
[`Workflow commands should earn their keep`](vibe-coding-notes.md#workflow-commands-should-earn-their-keep).

---

## PR #4 — Teaching register and `docs/learn/`

**Merged:** 2026-04-11  |  **Branch:** `learning/docs-and-context`
**Explainer:** [`prs/pr-004-docs-learn-teaching-register.md`](prs/pr-004-docs-learn-teaching-register.md)

PR #4 is where the repo stopped treating "things the AI should know" and
"things the human author will want to remember later" as the same category of
documentation. Before this PR, the root AI files were doing too much work:
they were carrying rules, narrative, and teaching context that really wanted
their own home. That made the always-loaded prompts bigger and made the
learning trail harder to revisit.

The fix was to create `docs/learn/` as a dedicated teaching layer. The AI
context files stayed short and operational, while `python-notes.md`,
`glossary.md`, `interview-prep.md`, `journey.md`, and `vibe-coding-notes.md`
became the place where the project explains itself in plain language. That
split also made the later `docs/ai/` operator-guide work in PR #5 possible:
the repo now had a clean difference between source docs, routing docs, and
tool adapters.

The takeaway: good AI context is not "put every useful sentence into the
startup prompt." It's deciding which knowledge needs to be always loaded,
which knowledge should be looked up on demand, and which knowledge exists for
the human maintainer rather than the model.

AI workflow concepts introduced:
[`AI context file`](glossary.md#ai-context-file),
[`context window`](glossary.md#context-window-token-budget).
Vibe-coding lessons:
[`Multi-tool context strategy`](vibe-coding-notes.md#multi-tool-context-strategy).

---

## PR #3 — Phase 1 Foundations (F1–F8)

**Merged:** 2026-04-11  |  **Branch:** `plan/phase-1-foundations`
**Explainer:** [`prs/pr-003-phase-1-foundations.md`](prs/pr-003-phase-1-foundations.md)

Phase 1 was about to start. Before writing a single line of Phase 1 code, we
ran the existing `docs/PLAN.md` through a Codex review, and Codex came back
with a set of real, subtle problems the plan hadn't addressed. The biggest
one: the plan said "VAD silence-stripping is part of the audio extraction
path," but Phase 3 (SRT/markdown formatters) needed segment timestamps on the
**original** media timeline. If we stripped silence from the canonical audio,
every `.srt` caption would drift by however much silence got removed from
before it. That's the kind of bug that ships, and then a user notices their
subtitles are 11 seconds out of sync, and three hours later someone figures
out it was the VAD filter. Much better to catch it in the plan.

So PR #3 is a **doc-only** PR that defines eight binding contracts — F1
through F8 — that every later phase has to respect. The most important ones:

- **F1 — sync through Phase 4.** Every library we actually use
  (`ffmpeg-python`, `yt-dlp`, `faster-whisper`, Google SDKs) is blocking-native.
  The original plan said "all I/O must be `async def`," which is Node.js
  thinking applied to a Python project. We explicitly committed to sync code
  through Phase 4 and will only revisit async when Phase 5 (cloud providers)
  introduces a real concurrency need — overlapping uploads, streaming
  responses, that kind of thing. **Java analogue:** writing every method
  `CompletableFuture<T>` because "async is modern" when your dependencies
  are all synchronous JDBC anyway.
- **F2 — `PreparedMedia`, the source→pipeline contract.** Sources (local
  files, YouTube, Google Drive, future cloud buckets) all return a single
  dataclass the rest of the pipeline consumes. The pipeline **never** sees a
  raw URI after the first step. **Java analogue:** a DTO — a plain data
  object at the boundary between layers so downstream code doesn't have to
  know whether the input came from disk or HTTP. Defining this in Phase 1
  costs ~30 lines of Python; retrofitting it in Phase 4 would mean rewriting
  every source we'd already shipped.
- **F3 — versioned composite cache keys.** The original plan said
  `SHA256(file + quality)`. That's not enough. If you change the model
  revision, the language override, or the VAD mode, the cache will hand back
  a stale transcript that *looks* right but isn't. We now hash a composite of
  audio bytes, provider id, model id, model revision, language, VAD mode, and
  a `PIPELINE_SCHEMA_VERSION` integer. Bump the version → old entries are
  safely invalidated. **Java analogue:** `serialVersionUID` on a serializable
  class, for the same reason.
- **F4 — two-gate spend.** "API key configured" and "provider will be used"
  must be separate decisions. The old plan implied that if `DEEPGRAM_API_KEY`
  was in your `.env`, Deepgram was in play. That silently breaks the
  "$0 default" promise. We now have Gate 1 (is the key present?) and Gate 2
  (does the current `--budget` allow paid use?). You need both. Paid LLM
  fallback also requires an explicit `--allow-paid-llm` flag. **Java
  analogue:** Spring's defense-in-depth — having `@PreAuthorize` on a
  controller isn't enough if your service layer also skips the check.
- **F5 — `RunWorkspace`.** Every CLI invocation gets exactly one temp directory,
  managed by a context manager. Sources write into it. Extractors write into
  it. Atomic output writes (`write-to-tmp + os.replace`) land through it. On
  normal exit, exception, or Ctrl-C, the `try/finally` cleanup deletes it.
  No more leaked WAVs. **Java analogue:** a single `try-with-resources` at
  the top of a pipeline method, not five nested ones buried in the middle.

The other three contracts — F6 (model download preflight), F7 (fixtures and
stubs strategy), F8 (observability minimums) — are less dramatic but each
catches a class of footgun we would otherwise have shipped and regretted.

The takeaway: **the cheapest time to fix an architectural mistake is before
the code exists**. The Codex review was 30 minutes, the plan edit was 2 hours,
and every one of those fixes would have cost days if we'd hit them after
Phase 1. This PR is the first test of "let the plan review catch the bug,
not the code review."

Python idioms worth noting from this PR (all in the plan, not in code yet):
[`frozen dataclasses`](python-notes.md#frozen-dataclasses),
[`Literal` types](python-notes.md#literal-types),
[context managers](python-notes.md#context-managers).
AI/ML concepts introduced:
[VAD (as a sidecar, not a transform)](glossary.md#vad),
[`faster-whisper`](glossary.md#faster-whisper),
[prompt caching](glossary.md#prompt-caching),
[LiteLLM](glossary.md#litellm),
[LangGraph](glossary.md#langgraph),
[provider abstraction](glossary.md#provider-abstraction).

---

## PR #2 — Project rename: Transcriber → SSM-Transcriber

**Merged:** 2026-04-11  |  **Branch:** `phase/0-skeleton`
**Explainer:** [`prs/pr-002-phase-0-rename.md`](prs/pr-002-phase-0-rename.md)

A short retrospective entry: the project was originally created as `Transciber`
(typo), renamed to `Transcriber`, and then renamed again to `SSM-Transcriber`
to disambiguate from the many other tools with similar names. The lesson
here isn't technical — it's that naming is a branding decision that's cheap
to make *before* dependencies pin themselves to your package name, and
extremely expensive afterward. PR #2 touched the GitHub repo, the `pyproject.toml`
package name, the CLI entry point, every `import` path, and all five AI
context files. Doing this on Phase 0 was a few minutes of churn; doing it in
Phase 3 would have been a half-day of mechanical find-and-replace plus a
broken `main` for anyone with the old name cached.

**Java analogue:** changing your `groupId` / `artifactId` in Maven after
other modules already depend on it.

---

## PR #1 — Phase 0: project skeleton

**Merged:** 2026-04-11  |  **Branch:** `phase/0-skeleton`
**Explainer:** [`prs/pr-001-phase-0-skeleton.md`](prs/pr-001-phase-0-skeleton.md)

The first real PR. It set up a runnable (if stubbed) Python project with:

- [`pyproject.toml`](../../pyproject.toml) — the single source of truth for
  dependencies, Python version, and CLI entry points. **Java analogue:**
  `pom.xml`, except `pyproject.toml` is a PEP 621 standard so every modern
  Python tool reads it (unlike the `setup.py` / `setup.cfg` / `requirements.txt`
  fragmentation of the 2010s).
- [`uv.lock`](../../uv.lock) — a fully resolved dependency lockfile, committed
  to the repo. **Java analogue:** the effective POM plus a pinned dependency
  tree, except the lockfile is *the* input the next `uv sync` uses, rather
  than something Maven re-derives. In Python-land, applications pin their
  lockfile; libraries don't. This project is an application, so the lockfile
  is tracked.
- `uv` as the package manager. It's written in Rust, 10–100× faster than
  `pip`, and handles virtual-env creation, dependency resolution, and script
  execution from one tool. **Java analogue:** Maven + a much faster local
  install cache + `mvnw`, all in one binary.
- `typer` for the CLI, with Rich for pretty output. **Java analogue:**
  `picocli` with annotation-driven command definitions. See
  [`python-notes.md#typer-and-annotated`](python-notes.md#typer-and-annotated)
  for how the CLI is wired.
- `pydantic-settings` for config. Reads environment variables and `.env` into
  a validated settings object. **Java analogue:** Spring's
  `@ConfigurationProperties` — a declarative bridge from env-vars/files into
  a typed configuration bean, with validation errors at startup instead of
  at first use.
- `ruff` (linter + formatter, single Rust binary) and `mypy` (static type
  checker) wired into CI via a GitHub Actions workflow. **Java analogues:**
  `ruff` ≈ Checkstyle + Spotless rolled into one; `mypy` is the closest
  thing Python has to the compile step you get for free in Java. Python's
  runtime never type-checks anything, so `mypy` is what catches
  "`str.lower()` called on an `Optional[str]`" *before* a user hits it.
- `pytest` for the test harness — more flexible than JUnit because test
  functions are just plain `def test_...` functions in any file matching
  `test_*.py`. No `@Test` annotation required; no class hierarchy required.
- Five AI root adapters (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`,
  `.cursorrules`, `.github/copilot-instructions.md`) so any AI tool the author
  uses — Claude Code, Codex, Gemini CLI, Cursor, Copilot — starts with the
  same startup guardrails. In PR #5 this grows into a fuller system with
  `docs/ai/README.md` and runbooks, but the underlying reason is the same:
  every tool should start from the same rules.

The PR ended in a stubbed `uv run ssm-transcriber --help` that prints the
command tree but refuses to actually transcribe anything. That's Phase 0's
success criterion — the scaffolding exists, the CI is green, and Phase 1 has
a clean runway.

The thing this PR is *most* useful for as a learning artifact is: it's a
snapshot of a modern (2025) Python project starter kit. If you want to build
another Python CLI from scratch, clone Phase 0 and delete the transcribe
command.
