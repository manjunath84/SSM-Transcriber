# Interview Prep

> Curated index of what this project can answer in an AI/ML engineering
> interview. **Every entry traces back to a real file or plan section in
> this repo** — if you can't point at the code or the plan, it doesn't
> belong here.
>
> The goal isn't to replace general interview prep (transformers, embeddings,
> distributed training, etc.) — it's to make sure that when an interviewer
> asks "tell me about a project you've built," you have a specific,
> well-reasoned answer with receipts. This project is small enough to fit
> in one conversation and opinionated enough to be interesting to talk about.
>
> **How to use this file.** When you sit down to prep, skim the headings,
> pick 2–3 stories per category, and practice speaking them out loud. The
> pointers go back to `journey.md` / `glossary.md` / `python-notes.md` /
> `prs/` so you can re-read the full context, but in the interview you
> deliver the short version.

---

## Project pitches (rehearse these verbatim)

### 30-second version
> I'm building **SSM-Transcriber**, an audio/video transcription pipeline
> that's local-first and provider-swappable. The default run is zero cost —
> it uses `faster-whisper` on the local machine — and every cloud provider
> (Deepgram, AssemblyAI, OpenAI Whisper, LLM post-processing) is explicitly
> opt-in behind a budget flag. I'm building it with a vibe-coding workflow —
> five AI context files keep Claude Code, Codex, Gemini CLI, Cursor, and
> Copilot all generating code that matches the same conventions. I'm using
> it as the vehicle for my transition from Java backend engineering to AI/ML
> engineering, and I've been deliberate about turning every architectural
> decision into a documented learning artifact so the repo doubles as a
> portfolio piece.

### Two-minute version
Add to the 30-second version:

> The project is organized in phases — Phase 0 is the skeleton (CLI, config,
> CI), Phase 1 is local transcription, Phase 2 adds YouTube, Phase 3 adds
> output formats, Phase 4 adds Google Drive, Phase 5 adds cloud transcription
> providers, and Phase 6 adds LLM summarization and a LangGraph multi-agent
> foundation. Before starting Phase 1 I ran the plan through an independent
> AI code reviewer and caught **eight architectural issues** that would have
> been expensive to fix after code existed — things like the cache key being
> under-specified so schema changes would return stale results, the cost
> model leaking "API key exists" into "API key will be used," and VAD
> silence-stripping that would have drifted SRT subtitle timestamps by
> however much silence got removed. I turned those fixes into a binding
> "Phase 1 Foundations" contract (F1–F8) that every later phase has to
> respect. The repo has a `docs/learn/` folder where I keep a running
> narrative of what was built and why — it's part portfolio, part
> study guide.

### Five-minute walkthrough
Hit these points in order, ~30 seconds each:

1. **The problem.** "I wanted to transcribe audio from local files and
   YouTube without paying per minute, because I was processing a lot of
   podcast and meeting recordings. Existing tools either cost money per
   minute or had no cost controls at all."
2. **The architecture choice that matters most.** "Local-first, cloud-optional.
   `faster-whisper` runs on the local machine with no API key. Cloud
   providers are registered behind a provider abstraction with shared
   transcription and cost-estimation rules; the budget router enforces a
   two-gate check — 'is the key configured' and 'is paid use allowed' —
   before ever authorizing a cloud call. This is the discipline that kept
   '`$0` default' from being a lie."
3. **The subtlest bug I caught before writing code.** "VAD — voice activity
   detection — would have been the 'obvious' optimization: strip silence
   before transcribing. But the SRT subtitle formatter in Phase 3 depended
   on segment timestamps on the original media timeline. If I stripped
   silence, every subtitle would drift by the amount of silence removed.
   Bug in the plan, not in the code. Fix was to treat VAD as a **sidecar**
   — compute `speech_regions` as a separate table and use it only for cost
   estimation and reduced cloud uploads, never as a transform of the
   canonical audio."
4. **The cost model.** "Every cloud call shows an estimated cost before
   running and requires confirmation. LLM post-processing defaults to a
   free tier (Groq) and requires an explicit `--allow-paid-llm` flag to
   fall back to Anthropic, Gemini, or OpenAI — no silent escalation. The
   estimated cost is computed from `speech_duration` (the VAD sidecar
   output), not total media duration, so users see the billable figure."
5. **What's next.** "Phase 1 implementation, then YouTube, then output
   formats, then cloud providers, then LLM post-processing, then a
   LangGraph state machine that exposes the pipeline as an agent so a
   future Notes Agent can consume transcripts without re-transcribing.
   Every phase ends with a green PR merge to `main` — no phase branches
   hang around half-finished."

---

## Behavioral / STAR stories

Every story below is a real event captured in the repo. The format is
**Situation → Task → Action → Result** — practice each one out loud.

### "Tell me about a technical decision you made and the trade-offs"

**Story: VAD as a sidecar, not a transform** (PR #3 / Phase 1 Foundations F3 rationale).

- **Situation.** I was about to start Phase 1 of the project. The plan said
  to use VAD (voice activity detection) to strip silence from audio during
  extraction, saving 20–40% of billable minutes when routing to cloud.
- **Task.** Validate the plan before writing any code, by running it
  through an independent AI reviewer.
- **Action.** The reviewer flagged that Phase 3's SRT and markdown
  formatters depended on timestamps from the *original* media timeline.
  If I stripped silence during extraction, every timestamp in the cached
  transcript would be from the stripped timeline — and when the formatter
  emitted an SRT file, captions would drift by the amount of silence
  removed. I rewrote the plan to treat VAD as a **sidecar**: the canonical
  transcription runs on the full audio, and `speech_regions` is stored as
  a separate `[(start, end)]` table. The sidecar is consulted only for
  cost display and for building a reduced upload to the cloud — never as
  a transform of the canonical audio.
- **Result.** A class of bug that would have shipped silently (and then
  taken days to diagnose in the field) was caught with a plan edit before
  any code existed. Formalized as contract F3 / cost-section item 3 in
  `docs/PLAN.md`. The sidecar design has an explicit unit test in the
  Phase 1 plan: `short_speech_with_silence.wav` is a fixture with 3s of
  silence on either end, and the test asserts that segment timestamps
  match the original timeline ±200ms.

**Pointers:** [`journey.md` PR #3 entry](journey.md#pr-3--phase-1-foundations-f1f8),
[`glossary.md#vad`](glossary.md#vad),
[`prs/pr-003-phase-1-foundations.md`](prs/pr-003-phase-1-foundations.md).

### "Tell me about a time you caught a bug before it shipped"

Same story as above, or:

**Story: The "key configured" ≠ "key used" loophole** (Phase 1 Foundations F4).

- **Situation.** The plan said "cloud providers are only used when
  `TRANSCRIPTION_PROVIDER` env var is set." On paper, that sounds fine.
- **Task.** Confirm that the `$0 default` promise actually holds under
  realistic usage.
- **Action.** The reviewer pointed out that "having a `DEEPGRAM_API_KEY`
  in `.env`" and "Deepgram is authorized to run" were being treated as
  the same condition. A user might set a key for a one-off experiment,
  forget about it, and get surprise-charged on their next run. I
  introduced a **two-gate spend model**: Gate 1 (key configured) and
  Gate 2 (current budget allows paid use). Both gates are required.
  For LLM fallback, a third flag (`--allow-paid-llm`) is also required.
- **Result.** The cost promise now holds by construction, not by luck.
  Formalized as contract F4. The Phase 5 budget router logs the chosen
  provider and the *reason* at `INFO`, so the audit trail is in the logs.

**Pointers:** [`glossary.md#two-gate-spend-model`](glossary.md#two-gate-spend-model),
[`docs/PLAN.md` Phase 1 Foundations F4](../PLAN.md).

### "Tell me about a time you designed a boundary between two components"

**Story: `PreparedMedia`, the source→pipeline DTO** (F2).

- **Situation.** Phase 2 would add YouTube support (yt-dlp), Phase 4 would
  add Google Drive — each is a different "source" of audio, and each
  needs different fetch logic. The plan was originally going to pass raw
  URIs through to the pipeline and let each layer figure it out.
- **Task.** Define the contract between the source layer and the
  transcription pipeline before I'd written even one source.
- **Action.** Defined `PreparedMedia` as a frozen dataclass with
  `kind`, `original_uri`, `local_path`, `title`, `duration_seconds`,
  `workspace`, and `extra`. Sources return this; the pipeline never sees
  a raw URI after the first step. Phase 1 uses it with only `LocalSource`
  implemented. Phase 2 adds `YouTubeSource` without changing anything
  downstream. The resolver matches URLs by *hostname*, not scheme, so
  Google Drive doesn't accidentally collide with YouTube.
- **Result.** Boundary DTO formalized in F2. When Phase 2 lands, it'll
  be ~30 lines of new code, zero rewrites of Phase 1. If I hadn't defined
  this at Phase 1 time, Phase 2 would have rewritten every extractor
  and cache call site.

**Java analogue:** this is exactly what you'd do at a DDD boundary —
a value object carrying the data the downstream bounded context needs.
The interviewer will usually smile when you say this out loud.

**Pointers:** [`glossary.md#preparedmedia`](glossary.md#preparedmedia),
[`python-notes.md#frozen-dataclasses`](python-notes.md#frozen-dataclasses).

### "Tell me about a time you had to learn something new fast"

**Story: entire project.** You're a Java developer who picked up Python,
`uv`, `pydantic-settings`, `typer`, `ruff`, `mypy`, `faster-whisper`,
LangGraph vocabulary, and the agentic engineering mental model in a few
weeks. The `docs/learn/python-notes.md` and `docs/learn/glossary.md`
living docs are the **receipts** — they show exactly what you learned and
where each concept first mattered.

**How to tell it:** "I built the infrastructure so that every time I
encountered a new idiom or concept, I had to write a short entry about it
with a Java analogue. That forced me to genuinely understand it instead
of copy-paste-and-hope. The `python-notes.md` file is literally the
artifact of that learning process."

**Pointers:** [`python-notes.md`](python-notes.md), [`glossary.md`](glossary.md).

### "Tell me about a time you chose between two approaches"

**Story: sync vs. async (Phase 1 Foundations F1).**

- **Situation.** The AI context files originally said "all I/O methods must
  be `async def`." That's modern-Python-zeitgeist advice, but it
  contradicted the actual skeleton code (which was sync) and the library
  stack (every library I use — `ffmpeg-python`, `yt-dlp`, `faster-whisper`,
  Google SDKs — is blocking-native).
- **Task.** Pick one and commit to it explicitly.
- **Action.** Committed to **sync through Phase 4**, with an explicit
  revisit point at Phase 5 (cloud providers — the first place real
  concurrency could actually help). Reasoning: async is a tool for
  overlapping I/O on a native-async runtime. If every downstream call
  is blocking anyway, `async def` just adds ceremony without measurable
  benefit. Revisit when a real need appears, not before.
- **Result.** F1 formalized. The CLI stays single-threaded, the code is
  simpler, and the commitment is explicit so no one (human or AI) will
  drift back into "async all the things" by reflex.

**The interviewer's follow-up is usually: "Why would you revisit at
Phase 5?"** Answer: Phase 5 adds paid cloud providers. A user transcribing
a long file and a short file concurrently could benefit from running the
cloud uploads in parallel. That's a concrete case — you *measure* whether
async helps, and if it does, you introduce it then, not by speculation.

**Pointers:** [`docs/PLAN.md` F1](../PLAN.md),
[`journey.md` PR #3 entry](journey.md#pr-3--phase-1-foundations-f1f8).

### "Tell me about a time your automated tests failed to catch a bug"

**Story: The wrong rate constant that 12 weeks of unit tests missed** (PR #18).

- **Situation.** PR #12 shipped AssemblyAI support with a hardcoded rate
  constant `ASSEMBLYAI_RATE_PER_MINUTE_USD = 0.009`. The unit tests verified
  that the cost-estimation math was correct *relative to the constant* — 10
  minutes at $0.009/min = $0.09. Every test passed. The constant was 2.35x too
  high.
- **Task.** The PR #17 manual runbook required comparing the CLI's pre-run cost
  estimate against the actual AssemblyAI billing dashboard after a real
  transcription run. I had to run this check before declaring PR #17 done.
- **Action.** The dashboard showed $0.2415 for 63 minutes of audio. The CLI
  had quoted $0.567. I pulled two independent days of Cost dashboard data,
  computed the per-minute math ($0.0035/min base + $0.000333/min diarization),
  and confirmed the constants to 6 decimal places. PR #18 split the single
  constant into two empirically-verified ones and added a regression test
  that locks the rate against the real billing figure —
  `test_estimate_cost_matches_real_pr17_run`. A future rate change will fail
  that assertion and force re-verification against fresh dashboard data.
- **Result.** The bug had lived in the codebase through one full feature (Drive
  source passthrough, PR #17) without any test catching it. The structural
  defence turned out to matter: PR #15's brainstorm decision to skip
  per-minute estimates for Drive sources had inadvertently made Slice 2 immune
  to the bug class.

**The interviewer's follow-up is usually: "How did you make sure it wouldn't
happen again?"** Answer: two things. First, the new regression test locks the
rate against an empirical billing figure, not a computed value — the constant
*is* the thing being tested. Second, every manual runbook now includes a
cost-vs-dashboard comparison step, making the rate a thing you verify on every
real run, not something you trust once and forget.

**Pointers:** [`prs/pr-018-assemblyai-rate-constant-fix.md`](prs/pr-018-assemblyai-rate-constant-fix.md),
[`journey.md` PR #18 entry](journey.md#pr-18--fix-assemblyai-rate-constant--factor-in-diarization).

---

## System design

The project itself is a system design exercise. For each question below,
the "right" answer is a whiteboard that looks a lot like `docs/PLAN.md`.

### "Design a transcription pipeline that supports local files, YouTube, and Google Drive, with multiple transcription providers and a cost ceiling"

**Walk the interviewer through:**

1. **Input resolution.** Source resolver dispatches by URI shape; each
   source implements `prepare(uri, workspace) → PreparedMedia`. Hostname
   match for URLs, not scheme. F2.
2. **Run lifecycle.** Every invocation opens exactly one `RunWorkspace`
   (temp dir with `try/finally` cleanup). All temporary artifacts — the
   extracted WAV, the downloaded YouTube audio, the sidecar JSON, the
   pre-atomic output writes — live in the workspace. Ctrl-C still cleans
   up because the workspace is a context manager. F5.
3. **Extraction.** `ffmpeg-python` converts any input to 16 kHz mono WAV
   in the workspace. VAD runs as a **sidecar**, not a transform.
4. **Caching.** Before transcription runs, compute a **versioned composite
   cache key**: audio content SHA256 + provider id + model id + model
   revision + language override + VAD mode + `PIPELINE_SCHEMA_VERSION`.
   Cache hits return in ~1 ms with zero cost. F3.
5. **Provider abstraction.** `TranscriptionProvider` base class with
   `transcribe()` plus a shared pricing/estimation hook. Concrete providers:
   faster-whisper (local, $0), Deepgram, AssemblyAI, and OpenAI Whisper,
   with Hugging Face reserved as a later explicit-only hosted-provider
   experiment. Registry + factory.
6. **Budget router.** Two-gate spend check before any cloud call: is the
   key configured (Gate 1) AND is paid use allowed by `--budget` (Gate 2).
   Cost estimate is computed from `speech_duration` (VAD sidecar), shown
   to the user, and confirmed before running. F4.
7. **Output.** Formatter factory (`txt`, `srt`, `md`, `json`) takes a
   `TranscriptResult` and writes atomically via `os.replace` so a Ctrl-C
   during write doesn't truncate the output file.
8. **Retry.** Cloud calls are wrapped with `tenacity`: retry on 429/503/
   network timeout, exponential backoff, max 3 attempts, never retry on
   4xx (user error).
9. **Observability.** `logging` everywhere. Secrets redacted via
   `settings.redacted_dump()`.

**The system design follow-ups you'll get:**

- "What if the cloud call fails?" → Retry + clean error message with the
  workspace preserved for debugging if `--keep-temp` is set.
- "What about streaming transcription?" → Out of scope Phase 1–5. Would
  land in Phase 5+ with a new streaming provider class and some form of
  async (the actual reason to revisit F1).
- "How does the cache stay correct across model upgrades?" → Model
  revision is part of the cache key. Schema changes bump
  `PIPELINE_SCHEMA_VERSION` and old entries are invalidated by
  construction. F3.
- "How would you add a new source / provider / format?" → Each of these
  has a documented "Adding a new X" section in `CLAUDE.md`. Talk through it.

### "Design the cost-control layer for an LLM app"

The two-gate spend model (F4) is the answer. Walk through it:

1. Separate "configured" (key present) from "allowed" (current policy
   permits the call). Both required.
2. For LLM-specific flows, add a third flag (`--allow-paid-llm`) so that
   free-tier failures don't silently escalate to paid providers.
3. Estimate cost before the call, not after. Show it to the user.
   Require confirmation unless `--yes`.
4. Use VAD (or equivalent pre-filter) to estimate cost on the actually
   billable portion, not the total input size. `speech_duration`, not
   `total_duration`.
5. Log the provider choice and the reason at `INFO`. Audit trail matters.
6. For LLMs specifically: chunk long inputs, enable prompt caching, use
   cheapest-first fallback chains, never exceed the user's declared budget.

### "How would you cache expensive transcription results"

The versioned composite key (F3) is the answer. Key points:

- Cache key is not just `SHA256(audio)` — that would return stale results
  across model upgrades, language overrides, or VAD mode changes.
- The composite includes: audio content hash, provider id, model id,
  model revision, language override, VAD mode, and a schema version
  integer.
- Schema bump = safe invalidation of old entries by construction.
- Cache file layout: `~/.cache/transcriber/v{schema}/{digest}.json` so old
  schema versions can be garbage-collected with one `rm -rf`.
- Cache writes are atomic (write-to-tmp + `os.replace`) so a crash
  mid-write never leaves a corrupt cache file.
- The Java analogue is `serialVersionUID` — but applied to the *inputs*
  of a lookup, not to a serializable class.

### "How would you make the transcription pipeline 'agentic'?"

Phase 6b (LangGraph) is the answer. Key points:

- Wrap the existing pipeline stages (fetch, extract, transcribe, format)
  as **nodes** in a LangGraph state machine. Nodes read and write a
  shared `TranscriberState` Pydantic model.
- Nodes stay sync (F1); the graph boundary can go async internally if
  LangGraph needs it. Do **not** rewrite the sync pipeline into async
  just for LangGraph's sake.
- Expose a `transcription_complete` event at the end of the graph. A
  future Notes Agent (separate repo) subscribes to this event, consumes
  the transcript without re-transcribing (zero re-processing cost).
- This is a **forward-compatible** design: Phase 1–5 is sequential code,
  Phase 6b is a structural migration with no feature changes.
- The word "agentic" means *an LLM is in the control flow*. In Phase 6b
  there is no LLM in the control flow yet — the graph is just a structured
  way to express the pipeline. Phase 6c+ (future) would add an LLM planner
  that decides *which* nodes to run.

---

## Vibe coding / AI-assisted development

This is a **hot interview topic** in 2025–2026, especially for AI/ML
engineering roles. Interviewers want to know: do you ship with AI tools,
or do you just talk about them? This project has unusually specific
receipts.

### "How do you use AI tools in your development workflow?"

**Walk the interviewer through the SSM-Transcriber workflow:**

1. **Five root adapters, one operator guide.** Claude Code reads `CLAUDE.md`,
   Cursor reads `.cursorrules`, Copilot reads
   `.github/copilot-instructions.md`, Codex reads `AGENTS.md`, Gemini CLI
   reads `GEMINI.md`. Those root files keep the small set of startup guardrails
   inline, then route the tool to `docs/ai/README.md` for workflow routing and
   to `docs/PLAN.md` for detailed contracts.
2. **Plan review before code review.** Before Phase 1, the plan was sent
   to an AI reviewer. It found eight architectural issues — the most
   expensive classes of bug — before any code existed. "I catch
   architecture mistakes in plan documents, not in code reviews."
3. **"Don't do" lists as guardrails.** The adapter files include explicit
   prohibitions: no `async def`, no `os.environ`, no `print()`, no
   `SHA256(file + quality)` cache keys. These are more effective than
   positive instructions because they contradict the AI's training
   priors.
4. **Workflow-heavy tasks use runbooks, not memory.** Review, ship, and
   PR-prep steps are captured in runbooks and slash commands, so the AI
   has to produce a checklist or evidence table instead of improvising a
   vague "looks good."
5. **Verification after every AI-generated change.**
   `uv run pytest && uv run ruff check src/ && uv run mypy src/` — the
   AI's confidence is uninformative, only the test suite is reliable.

**The one-liner:** "I keep short tool-specific adapters for first-turn
safety, one operator guide for workflow routing, and explicit runbooks for
review/ship/PR prep so every AI tool behaves consistently without copying the
whole rulebook into every prompt."

**Pointers:** [`vibe-coding-notes.md`](vibe-coding-notes.md),
[`glossary.md#ai-context-file`](glossary.md#ai-context-file),
[`glossary.md#vibe-coding`](glossary.md#vibe-coding).

### "How do you ensure AI-generated code follows project conventions?"

**STAR story:**

- **Situation.** Five different AI tools, each with different training
  data and tendencies. Without guardrails, each tool generates code in
  its own style — some write `async def`, some use `os.environ`, some
  scatter `print()` debug statements.
- **Task.** Make every tool produce code that matches the project's
  actual conventions on the first try, without manual re-prompting.
- **Action.** Created per-tool context files with: (1) explicit code
  examples (the exact import path, the attribute naming style), (2)
  "What NOT to do" block with specific alternatives for each prohibition,
  (3) pointer to `docs/PLAN.md` as the single source of truth so rules
  aren't duplicated and drifting, (4) current-phase indicator so the AI
  doesn't try to implement Phase 5 features.
- **Result.** AI-generated code passes `ruff` + `mypy` on first
  generation much more reliably. The context files prevent entire classes
  of mistake — wrong config access, wrong async/sync choice, wrong cache
  key schema — before the code is even written.

### "What's the most effective technique you've found for AI-assisted development?"

**Answer:** "Code examples in context files. One 3-line code snippet
prevents more mistakes than a page of English prose. The AI
pattern-matches on code more reliably than on natural language. My context
files lead with `from transcriber.config import settings` — that exact
import line — to anchor the config access pattern."

**Second answer (for a deeper conversation):** "Plan review before code
review. Running a design doc through an AI reviewer before writing code
is the highest-leverage use of AI tools I've found. It catches cross-cutting
inconsistencies that humans miss because no human holds the entire document
in working memory at once."

### "What are the risks of AI-assisted development?"

**Answer with receipts:**

- **Confidence without correctness.** "The AI presents wrong code with
  the same confidence as correct code. That's why I run the full lint +
  type-check + test suite after every AI-generated change, not just at
  PR time."
- **Speculative documentation.** "AI tools will happily generate 500
  lines of documentation about things you haven't built. That's why this
  project has a 'living doc' rule: entries appear only when a real code
  change forces them."
- **Context window waste.** "If your context file is 300 lines of verbose
  prose, you've consumed tokens the AI needs for understanding your actual
  code. My context files are ~70 lines of rules. Narrative documentation
  lives in `docs/learn/` where humans read it."

---

## Vibe coding flashcards

| Topic | Flashcard pointer |
|-------|-------------------|
| What is vibe coding | [`vibe-coding-notes.md`](vibe-coding-notes.md#what-is-vibe-coding) |
| AI context files | [`vibe-coding-notes.md`](vibe-coding-notes.md#ai-context-files) |
| Multi-tool context strategy | [`vibe-coding-notes.md`](vibe-coding-notes.md#multi-tool-context-strategy) |
| Context window is currency | [`vibe-coding-notes.md`](vibe-coding-notes.md#context-window-is-currency) |
| "Don't do" lists beat "do" lists | [`vibe-coding-notes.md`](vibe-coding-notes.md#dont-do-lists-beat-do-lists) |
| Code examples as anchors | [`vibe-coding-notes.md`](vibe-coding-notes.md#code-examples-as-anchors) |
| Plan review before code review | [`vibe-coding-notes.md`](vibe-coding-notes.md#plan-review-before-code-review) |
| Living docs over upfront docs | [`vibe-coding-notes.md`](vibe-coding-notes.md#living-docs-over-upfront-docs) |
| Teaching register as forcing function | [`vibe-coding-notes.md`](vibe-coding-notes.md#teaching-register-as-a-forcing-function) |
| The verification loop | [`vibe-coding-notes.md`](vibe-coding-notes.md#the-verification-loop) |

---

## Python fluency flashcards

Interviewers sometimes sanity-check that you actually write Python, not
just talk about it. The cleanest way to practice: re-read
[`python-notes.md`](python-notes.md) and be ready to speak each entry in
30 seconds. Each one has a Java analogue for fast recall.

Quick list of what a Java dev should be fluent in after working on this
project:

| Topic | Flashcard pointer |
|-------|-------------------|
| Why `from __future__ import annotations` | [`python-notes.md`](python-notes.md#from-__future__-import-annotations) |
| `X \| Y` union syntax vs `Optional[X]` | [`python-notes.md`](python-notes.md#union-syntax) |
| `Literal` types for closed value sets | [`python-notes.md`](python-notes.md#literal-types) |
| `Annotated` for CLI metadata (`typer`) | [`python-notes.md`](python-notes.md#typer-and-annotated) |
| Frozen dataclasses (Java: `record`) | [`python-notes.md`](python-notes.md#frozen-dataclasses) |
| `@property` (Java: getter) | [`python-notes.md`](python-notes.md#property) |
| Context managers (Java: try-with-resources) | [`python-notes.md`](python-notes.md#context-managers) |
| `pathlib.Path` (Java: `java.nio.file.Path`) | [`python-notes.md`](python-notes.md#pathlib-path) |
| Module-level singletons (Java: Spring `@Bean`) | [`python-notes.md`](python-notes.md#module-level-singletons) |
| Lazy imports (startup speed / cycle breaking) | [`python-notes.md`](python-notes.md#lazy-imports) |

**Things not in `python-notes.md` yet that an interviewer might probe**
(they'll land as the code grows; practice them separately until then):

- Generators (`yield`) vs Java `Iterator`
- `async def` / `await` (the non-choice for this project)
- Decorators (Java: annotation processors)
- Metaclasses (almost never needed; a flag that you over-engineered)
- Duck typing vs structural typing (`typing.Protocol`)
- The GIL and why it matters for CPU-bound parallelism

---

## AI/ML concept flashcards (project-specific)

Everything in [`glossary.md`](glossary.md) is written to be interview-ready:
two-sentence definitions, one-sentence *why it matters here*. Re-read
the glossary once before an interview and practice speaking each entry
in 30 seconds.

The ones most likely to come up for AI/ML engineering interviews:

| Term | Why it's interview-relevant | Pointer |
|------|------------------------------|---------|
| VAD (as a sidecar) | Showcases "don't prematurely optimize in a way that destroys downstream data" | [`glossary.md`](glossary.md#vad) |
| `faster-whisper` | You'll be asked what you use for transcription; know why you picked it | [`glossary.md`](glossary.md#faster-whisper) |
| Prompt caching | Hot topic for LLM cost optimization; practice saying *how much* it saves | [`glossary.md`](glossary.md#prompt-caching) |
| LiteLLM | Signals you know the tooling landscape for LLM apps | [`glossary.md`](glossary.md#litellm) |
| LangGraph | Signals you understand agentic orchestration, not just chains | [`glossary.md`](glossary.md#langgraph) |
| Two-gate spend model | Original opinion — interviewers love engineers with opinions | [`glossary.md`](glossary.md#two-gate-spend-model) |
| Provider abstraction | Classic strategy pattern; translate from Java vocabulary | [`glossary.md`](glossary.md#provider-abstraction) |
| `RunWorkspace` | Resource lifecycle discipline — unusual and memorable | [`glossary.md`](glossary.md#runworkspace) |
| Versioned cache key | Cache invalidation is a famous hard problem; have an answer | [`glossary.md`](glossary.md#cache-key-versioned) |
| Agentic engineering | Vocabulary check — make sure the definition is precise | [`glossary.md`](glossary.md#agentic-engineering) |

**Broader AI/ML concepts not in this project's glossary** (know them for
the interview, study outside the repo):

- Tokenization, context windows, and how they affect cost
- Embeddings and vector search (for RAG, which this project doesn't do yet)
- Fine-tuning vs few-shot vs prompt engineering
- Hallucination and grounding strategies
- Evaluation: BLEU, WER (Word Error Rate — relevant for transcription!),
  human eval, LLM-as-judge
- Latency budgets and streaming responses
- Safety: jailbreaks, prompt injection, output filtering

---

## Evaluation questions (things this project doesn't answer yet)

Interviewers will sometimes push on *what you'd measure*. For SSM-Transcriber,
the honest answer is: evaluation is not Phase 0–6b. It would land later.
But you should have the *answer* ready:

- **Transcription quality:** Word Error Rate (WER) against a held-out set
  with known-good transcripts. Benchmark `faster-whisper` tiny/base/large
  against Deepgram Nova-2 on the same fixture set.
- **Timestamp accuracy:** mean absolute error of segment boundaries vs.
  a gold-standard alignment. This is why F3/F7 insist on
  `short_speech_with_silence.wav` as a fixture.
- **Cost accuracy:** predicted vs actual cost per cloud call, tracked
  over time, to catch provider pricing drift.
- **Cache hit rate:** what fraction of runs hit the cache, by source type
  and budget mode.
- **User-facing latency:** time-to-first-output, not just wall time.
- **LLM summary quality:** LLM-as-judge for summarize/clean outputs,
  with a gold set of reference summaries.

**If asked "how would you evaluate your own project?"** the honest answer
is: "I haven't built that yet, and I consider it a gap — it should be
Phase 7. My current guard is the F7 fixture strategy, which only verifies
that the pipeline runs and produces plausible output. Before shipping
this to any real user I'd want a WER benchmark harness and a cost
regression test." That kind of answer — "here's the gap, here's how I'd
close it" — is usually stronger than pretending everything is covered.

---

## The cheat-sheet one-liners

Memorize these. They're the sentences that make interviewers write things
down.

- **"Default run is $0. Every paid call is opt-in behind a budget flag
  and a confirmation prompt."**
- **"I treat VAD as a sidecar, not a transform, so segment timestamps
  stay truthful."**
- **"Cache keys are versioned composites — audio hash, provider, model,
  model revision, language, VAD mode, and a schema version integer. It's
  `serialVersionUID` applied to cache inputs."**
- **"I separate 'API key configured' from 'API key authorized.' Having
  a key in `.env` is necessary but not sufficient."**
- **"I picked sync over async because every library in my stack is
  blocking-native. Async would have been ceremony without a benefit to
  measure."**
- **"I caught the worst bug of the project in a plan review, before I'd
  written a line of code. That's the cheapest place to fix architecture
  mistakes."**
- **"The repo doubles as a learning artifact — `docs/learn/` has a
  running narrative, a Java-to-Python idiom reference, and a glossary
  of AI/ML concepts as they land in the code."**
- **"I keep short root adapters for each AI tool, one operator guide for
  workflow routing, and runbooks for the multi-step tasks. That keeps the
  tools aligned without copying the whole rulebook into every prompt."**
- **"The most effective AI technique I've found is code examples in
  context files. One 3-line snippet prevents more mistakes than a page
  of English."**
- **"I run my plan through an AI reviewer before writing code. That's
  how I caught the worst bug of this project — in a document, not in
  a codebase."**

---

## How to update this file

Like `python-notes.md` and `glossary.md`, this is a **living doc**. Update
rules:

1. **Add a story when a PR lands a decision worth talking about.** Not
   every PR needs an interview-prep entry. Bug fixes usually don't.
   Architectural decisions usually do.
2. **Every entry must be backed by something real in the repo.** No
   speculative "here's what I'd say if I'd done X." If it's not shipped,
   it's not a story yet.
3. **Practice out loud before each interview.** Reading this file is
   useless if you can't speak the STAR stories in 90 seconds each without
   notes.
4. **Prune entries when they stop being your best example.** Later PRs
   will produce better stories than PR #3 eventually. When they do,
   demote PR #3 from the top-billed story slot.
