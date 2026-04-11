# PR #3 — Plan: Phase 1 Foundations (F1–F8)

**Merged:** 2026-04-11  |  **Branch:** `plan/phase-1-foundations`  |  **Codex review:** yes (drove the PR)
**Journey entry:** [`../journey.md#pr-3--phase-1-foundations-f1f8`](../journey.md#pr-3--phase-1-foundations-f1f8)
**PR:** https://github.com/manjunath84/SSM-Transcriber/pull/3

## The problem in one paragraph

Phase 1 was about to start. Before writing any Phase 1 code, we ran the
existing `docs/PLAN.md` through a Codex CLI review, and it surfaced several
subtle but real problems that would each have cost days to fix after Phase 1
shipped. The biggest one: the plan said "strip silence with VAD during
audio extraction," but Phase 3 (SRT / markdown formatters) needed segment
timestamps on the **original** media timeline. If the canonical audio had
been silence-stripped, every subtitle would have drifted by the exact
amount of removed silence — the kind of bug that ships silently and gets
noticed three months later when a user complains their captions are 11
seconds off. The plan also had a self-contradicting cache-key definition
(it said one thing in the cost section and a stricter thing in Phase 1),
no story for "API key configured but spend not authorized," a vague
source→pipeline handoff that would force a Phase 1 rewrite when Phase 2
YouTube support landed, and an "all I/O is async" rule in the AI context
files that contradicted the synchronous skeleton code that actually existed.

## What changed (high level)

This is a **doc-only** PR. No source files, no dependencies. Seven files
changed: `docs/PLAN.md`, `README.md`, and all five AI context files
(`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`,
`.github/copilot-instructions.md`).

A new `docs/PLAN.md` section titled **"Phase 1 Foundations"** was inserted
between Phase 0.5 and Phase 1, defining eight binding contracts that every
later phase has to respect:

| # | Contract | One-line meaning |
|---|----------|-------------------|
| F1 | Sync through Phase 4 | No `async def` until there's a real concurrency need (Phase 5 at earliest). |
| F2 | `PreparedMedia` | Sources return a dataclass; the pipeline never sees raw URIs. |
| F3 | Versioned cache key | Composite of audio hash + provider + model + model revision + language + VAD mode + schema version. |
| F4 | Two-gate spend | "API key present" is necessary but not sufficient — budget flag must also allow it. Paid LLM requires a third flag. |
| F5 | `RunWorkspace` | One temp dir per CLI invocation, `try/finally` cleanup, atomic output writes. |
| F6 | Model download preflight | First-run `faster-whisper` model download is surfaced; `ssm-transcriber models download` prefetches. |
| F7 | Fixtures + stubs | `tests/fixtures/` for speech/video, `tests/stubs/` for yt-dlp/providers/LLMs, integration lane gated on `SSM_INTEGRATION=1`. |
| F8 | Observability | `logging` everywhere under `src/`, `settings.redacted_dump()` for diagnostic output. |

Beyond defining F1–F8, the PR also:

- **Rewrote cost-section item 3** so VAD is now framed as a **sidecar**
  (`speech_regions` on the original timeline, used for cost estimation and
  reduced cloud uploads) rather than a transform of the canonical audio.
- **Rewrote cost-section item 4** to defer to F3 for the cache-key
  schema, so there is exactly one place in the plan that says what a
  cache key looks like.
- **Rewrote the Phase 1 body** to use the new contracts end-to-end: the
  pipeline flow diagram now shows `RunWorkspace` → `LocalSource.prepare` →
  `PreparedMedia` → extractor → VAD sidecar → transcriber → atomic write.
- **Fixed the Phase 2 resolver example** to match URLs by hostname
  (`urlparse(uri).hostname in YOUTUBE_HOSTS`) instead of matching any
  `http://` or `https://` URL as YouTube. The old rule would have collided
  with Phase 4 Google Drive as soon as it landed.
- **Rewrote the Phase 5 budget router** to enforce Gate 1 (configured) and
  Gate 2 (allowed) as separate checks. `--budget free` now rejects any
  paid provider regardless of which keys are set.
- **Updated Phase 6a** so LLM fallback from free (Groq) to paid (Anthropic,
  Gemini, OpenAI) requires `--allow-paid-llm` in addition to the existing
  cost prompt. No silent escalation.
- **Relaxed the Phase 6b node description** so sync Phase 1–5 code can be
  wrapped as LangGraph nodes without rewriting everything async.
- **Reconciled every AI context file** so the rules now say the same
  thing. `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`, and
  `.github/copilot-instructions.md` all agree: sync through Phase 4,
  versioned cache keys, two-gate spend, `PreparedMedia`, `RunWorkspace`.
  Any future conflict: `docs/PLAN.md` wins.
- **Updated `README.md`** with a first-run `faster-whisper` model download
  note under Quick start, ticked the Phase 0 checkbox, and pointed at
  Phase 1 Foundations.

## Why this approach

Three choices to call out:

1. **Fix in the plan, not in the code.** The cheapest moment to correct an
   architectural mistake is before any code exists. VAD-as-transform would
   have been a cross-cutting rewrite once Phase 3 shipped; VAD-as-sidecar
   is a doc change now.
2. **Versioned composite cache key, not just "hash the file harder".** The
   alternative is to cache by audio content and hope nothing else ever
   affects the output. That fails the moment we change a model revision,
   the language override, or the VAD mode. The `PIPELINE_SCHEMA_VERSION`
   integer makes schema migrations free: bump it, old entries are
   invalidated in one line.
3. **Two-gate spend, not one.** "Key present means key will be used" is
   how people accidentally ship paid calls. Separating "configured" from
   "allowed" costs a few lines of router logic and removes an entire class
   of "why did I get charged $12" bug.

The alternative considered for all of this was: ship Phase 1 now, fix in
Phase 1.5. Rejected because **the review cost of Phase 1 was about to
multiply by the number of F-contracts we were punting**, and because a
doc-only change can be reviewed in an afternoon while a code rewrite
cannot.

## New Python idioms introduced

The plan *describes* idioms that Phase 1 will use but that no code in this
PR introduces. These land in the repo with Phase 1's implementation PR:

- [`frozen dataclasses`](../python-notes.md#frozen-dataclasses) — F2 `PreparedMedia`, F3 `CacheKey`
- [`Literal` types](../python-notes.md#literal-types) — F2 `SourceKind`
- [Context managers](../python-notes.md#context-managers) — F5 `RunWorkspace`

## New AI/ML concepts introduced

- [VAD as sidecar](../glossary.md#vad) — the timestamp-fidelity rationale
- [Versioned cache key](../glossary.md#cache-key-versioned)
- [Two-gate spend model](../glossary.md#two-gate-spend-model)
- [`PreparedMedia`](../glossary.md#preparedmedia) — the source→pipeline DTO
- [`RunWorkspace`](../glossary.md#runworkspace) — the per-run temp dir owner

## What a reviewer should notice

- **The anchor link from README.md** into `docs/PLAN.md` Phase 1
  Foundations needs to resolve on GitHub. Doc changes that *look* linked
  but don't actually resolve are a classic review miss.
- **Every AI context file says the same thing now.** Spot check:
  `grep "async def" CLAUDE.md AGENTS.md GEMINI.md .cursorrules
  .github/copilot-instructions.md` should return only the Phase 6b
  LangGraph note, nothing else.
- **No source code changed.** If any file under `src/` shows up in the diff,
  something went wrong — this PR was supposed to be pure planning.

## Interview angle

This PR is the single highest-signal story in the project so far — multiple
interview questions map to it. Captured in detail in
[`interview-prep.md`](../interview-prep.md). Short versions:

- **Story type:** bug-I-caught-before-shipping / trade-off / technical decision
- **Hook #1 — "Tell me about a bug you caught before it shipped":**
  *"I caught the worst bug of the project in a plan review, before I'd
  written a line of code. The plan said to strip silence with VAD during
  audio extraction, but Phase 3 needed original-timeline timestamps — any
  silence removed would have drifted every subtitle. The fix was to treat
  VAD as a sidecar, not a transform."*
  → [`interview-prep.md` § "Tell me about a technical decision you made"](../interview-prep.md#tell-me-about-a-technical-decision-you-made-and-the-trade-offs)
- **Hook #2 — "How do you design cost controls for an LLM app?":**
  *"I separate 'API key configured' from 'API key authorized.' Having a
  key in `.env` is necessary but not sufficient — the budget flag must
  also permit paid use. Three gates total for LLM fallback."*
  → [`interview-prep.md` § "Design the cost-control layer for an LLM app"](../interview-prep.md#design-the-cost-control-layer-for-an-llm-app)
- **Hook #3 — "How do you handle cache invalidation?":**
  *"Versioned composite cache keys. Audio hash plus provider plus model
  plus model revision plus language plus VAD mode plus schema version.
  It's `serialVersionUID` applied to cache inputs — schema bumps
  invalidate old entries by construction."*
  → [`interview-prep.md` § "How would you cache expensive transcription results"](../interview-prep.md#how-would-you-cache-expensive-transcription-results)
- **Hook #4 — "Sync or async — how do you decide?":**
  *"Every library in my stack is blocking-native. Async would have been
  ceremony without a benefit to measure. I committed to sync through
  Phase 4 and an explicit revisit point at Phase 5, when paid cloud
  uploads give concurrency a real reason to exist."*
  → [`interview-prep.md` § "Tell me about a time you chose between two approaches"](../interview-prep.md#tell-me-about-a-time-you-chose-between-two-approaches)

## Further reading

- [Codex CLI](https://github.com/openai/codex) — the reviewer that produced
  the findings this PR responds to
- `docs/PLAN.md#phase-1-foundations-contracts-that-later-phases-depend-on` —
  the full F1–F8 section this PR added
- [Silero VAD](https://github.com/snakers4/silero-vad) — the VAD model
  `faster-whisper` uses internally, for background on why "strip silence"
  is a lossy operation on the timeline
