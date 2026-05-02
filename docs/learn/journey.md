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
