# Glossary

> Living doc. AI/ML, agentic-engineering, audio-processing, and
> vibe-coding terms as they appear in this codebase. Plain language,
> two-sentence definitions. Each entry cites where the concept shows up
> in the repo so you can see it in context.
>
> Alphabetical. Add an entry only when a real file or plan section forces
> you to.

---

## Agentic engineering

The discipline of building software where an **LLM is part of the control
flow**, not just a feature. An agentic system receives a goal, plans its own
steps, calls tools or sub-agents, observes results, and iterates until the
goal is met or a budget is exhausted — as opposed to a traditional program
where the control flow is hand-written by the author.

This project is "agentic" because Phase 6b wraps the transcription pipeline
as a LangGraph state machine whose nodes are tools an LLM planner *could*
drive. In Phase 1–5 there is no LLM in the control flow; the agentic
vocabulary is a forward-compatibility choice, not a Phase 1 feature.

**Where it shows up:** `docs/PLAN.md` Phase 6b.

---

## AI context file

A file at the repo root that an AI coding tool reads automatically when it
opens a session. Each tool has its own convention: Claude Code reads
`CLAUDE.md`, Cursor reads `.cursorrules`, Copilot reads
`.github/copilot-instructions.md`, Codex reads `AGENTS.md`, Gemini CLI
reads `GEMINI.md`. In this repo the root files are compact adapters: they keep
startup guardrails inline, then route the tool to `docs/ai/README.md` for
workflow routing and to `docs/PLAN.md` / `docs/learn/README.md` for the
authoritative rules.

**Java analogue:** `.editorconfig` + `checkstyle.xml` + `CONTRIBUTING.md`
rolled into one, except read by your AI pair programmer instead of a
static analysis tool.

**Where it shows up:**
[`CLAUDE.md`](../../CLAUDE.md),
[`AGENTS.md`](../../AGENTS.md),
[`GEMINI.md`](../../GEMINI.md),
[`.cursorrules`](../../.cursorrules),
[`.github/copilot-instructions.md`](../../.github/copilot-instructions.md).
Operator guide in [`../ai/README.md`](../ai/README.md).
Design rationale in [`vibe-coding-notes.md#ai-context-files`](vibe-coding-notes.md#ai-context-files).

---

## Cache key (versioned)

A composite hash of every input that could change the correctness of a
cached result. In this project (F3), the cache key is a hash of:
audio content + provider id + model id + model revision + language override
+ VAD mode + `PIPELINE_SCHEMA_VERSION`. Bumping the schema version
invalidates every old entry safely — the old keys can no longer collide.

**Java analogue:** `serialVersionUID`, applied to the *inputs* of a cache
lookup rather than to a serializable class.

**Where it shows up:** `docs/PLAN.md` Phase 1 Foundations F3;
planned for `src/transcriber/core/cache.py` in Phase 1.

---

## Context window (token budget)

The fixed-size buffer of text an LLM can "see" during one interaction. For
coding assistants this typically ranges from 8K to 200K tokens depending on
the model. Every token occupied by a context file, a prompt, or retrieved
code is a token *not* available for generating or understanding new code.

**Why it matters for vibe coding.** Context window is the fundamental
resource constraint of AI-assisted development. If your AI context files
are 500 lines of verbose prose, they consume tokens that should be holding
your actual source code. This project keeps context files to ~60–80 lines
each and pushes narrative documentation into `docs/learn/` where it's
read by humans, not by AI.

**Where it shows up:** design rationale in
[`vibe-coding-notes.md#context-window-is-currency`](vibe-coding-notes.md#context-window-is-currency).

---

## `faster-whisper`

A re-implementation of OpenAI's Whisper transcription model that runs 3–5×
faster on the same hardware because it's built on `CTranslate2` (an
efficient inference runtime) instead of PyTorch. It downloads model weights
(from ~75 MB for `tiny` to ~3 GB for `large-v3`) on first use and caches
them under `~/.cache/huggingface/`. It supports CPU, CUDA, and Apple Metal.

**Why it matters here.** It's the default transcription provider and the
reason the project's default run is $0: no API key, no network round-trip
per request (after the first-run download), and it's fast enough on a
modern laptop to be usable in real time.

**Where it shows up:** listed as the first dependency in
[`pyproject.toml`](../../pyproject.toml); wrapped in
`src/transcriber/core/transcriber.py` starting in Phase 1.

---

## LangGraph

A graph-structured orchestration library from LangChain, for building
**stateful, multi-step workflows** where nodes are functions that read
and write a shared state object. Unlike a plain LangChain chain, a
LangGraph graph can loop, branch conditionally, and checkpoint, which is
what makes it useful as the backbone of an agent.

**Why it matters here.** Phase 6b migrates the existing (sync) pipeline to
LangGraph nodes so that Phase 6c+ can add an LLM planner on top without
rewriting the pipeline. Phase 1 does **not** use LangGraph — the first
version is a plain sequential function call. LangGraph lands when the
simpler design has proven it works.

**Where it shows up:** `docs/PLAN.md` Phase 6b;
planned for `src/transcriber/agents/` starting in Phase 6b.

---

## LiteLLM

A thin Python library that presents a unified OpenAI-compatible interface
to many LLM providers (OpenAI, Anthropic, Google, Groq, Cohere, local
Ollama, and ~100 others). You call `litellm.completion(model="gpt-4o", ...)`
or `litellm.completion(model="claude-haiku-4-5", ...)` and it translates to
the right provider's SDK behind the scenes.

**Why it matters here.** Phase 6a uses LiteLLM as a router with a
cheapest-first fallback chain (Groq free tier → Gemini Flash → Claude Haiku)
so the author can swap providers without touching pipeline code. Per F4,
paid fallback requires `--allow-paid-llm` — LiteLLM is the *mechanism*, F4
is the *policy*.

**Java analogue:** think of it as a JDBC-like driver layer for LLMs. The
same SQL works against MySQL or Postgres; the same LiteLLM call works
against OpenAI or Anthropic.

**Where it shows up:** `docs/PLAN.md` Phase 6a;
planned for `src/transcriber/llm/provider.py` in Phase 6a.

---

## `PreparedMedia`

The name of the dataclass (F2) that every media source in this project
returns after it has fetched or resolved the input. It carries the original
URI, a local file path (always present), optional metadata like title and
duration, and a reference to the `RunWorkspace` that owns cleanup. The
pipeline never sees a raw URI after the first step — it sees a
`PreparedMedia`.

**Java analogue:** a boundary DTO between the "source" layer and the
"pipeline" layer. Downstream code doesn't care whether the audio came from
disk, YouTube, or Google Drive; it only sees the common value object.

**Where it shows up:** `docs/PLAN.md` Phase 1 Foundations F2;
planned for `src/transcriber/sources/base.py` in Phase 1.

---

## Prompt caching

An Anthropic API feature (and similar features in other providers) that
lets you mark part of a prompt — typically a long system prompt or tool
schema — as "cached". Subsequent requests within ~5 minutes that reuse the
same cached prefix pay only ~10% of the normal token cost for that prefix.

**Why it matters here.** Phase 6a enables prompt caching for every
Anthropic call. Summarize/clean tasks have a long, stable system prompt and
a short, variable transcript tail — the system prompt gets cached, so a
second summarization within five minutes costs almost nothing extra. This
is the difference between $0.25/1M tokens and roughly $0.025/1M tokens on
the cached portion.

**Where it shows up:** `docs/PLAN.md` Phase 6a ("prompt caching enabled for
Anthropic calls").

---

## Provider abstraction

A general software pattern: define a base interface and ship multiple
implementations that callers can swap without code changes. In this project,
`TranscriptionProvider` (Phase 5) has `faster_whisper`, `deepgram`,
`assemblyai`, and `openai_whisper` implementations, all exposing the same
`transcribe()` method plus a shared pricing/estimation hook. A registry +
factory decides which one to load based on config. Hugging Face may join
later as an explicit-only hosted provider, but not until its pricing and
backend determinism are documented well enough to fit the repo's cost rules.

**Java analogue:** the strategy pattern, or — more directly — JDBC drivers.
You code against `Connection` / `PreparedStatement`, and `DriverManager`
loads the right driver based on the JDBC URL. Here, `get_provider("deepgram")`
plays the `DriverManager` role.

**Why it matters here.** It's what the "$0 default, paid upgrade available"
promise is built on. Swapping providers must be possible without touching
the pipeline, formatters, or CLI — the provider boundary is where the
variability lives, including the fact that not every hosted backend exposes
a neat fixed per-minute price.

**Where it shows up:** `docs/PLAN.md` Phase 5;
planned for `src/transcriber/providers/` in Phase 5.

---

## Runbook

A short, task-specific workflow document that tells an AI tool how to perform a
multi-step repo operation without turning that workflow into a permanently
auto-loaded prompt. In this repo, runbooks exist for review, shipping, PR prep,
and phase-audit work — the places where a checklist and output format save
real effort.

**Where it shows up:** `docs/ai/runbooks/`.

---

## `RunWorkspace`

The name of this project's per-invocation temp-directory manager (F5). One
`RunWorkspace` is created at the CLI boundary, passed down through sources,
extractors, and cache writers, and deleted in a `try/finally` on exit
(including Ctrl-C). It is the single owner of all temporary artifacts for
a given run.

**Why it matters here.** Without a run-scoped workspace, every module that
needs a temp file invents its own `tempfile.mkdtemp()` and the cleanup
story becomes "whoever calls `rm -rf` last wins." With one, Ctrl-C during
a 45-minute transcription still leaves the filesystem clean.

**Where it shows up:** `docs/PLAN.md` Phase 1 Foundations F5;
planned for `src/transcriber/core/workspace.py` in Phase 1.

---

## Slash command

A tool-specific command that loads a saved prompt or workflow by name instead
of making the user restate it in every session. In this repo, Claude Code slash
commands are intentionally limited to workflow-heavy tasks that produce a real
artifact or checklist, such as review and ship preparation.

**Where it shows up:** `.claude/commands/`.

---

## Two-gate spend model

This project's policy (F4) for when a paid API call is permitted. A paid
call requires **both** Gate 1 ("the API key is configured") **and** Gate 2
("the current budget flag allows paid use"). Having a `DEEPGRAM_API_KEY` in
your `.env` does not by itself authorize Deepgram to be called; `--budget`
must also permit it. For LLM fallback, a third gate is required:
`--allow-paid-llm`.

**Why it matters here.** It's how the "$0 default" promise survives contact
with reality. The failure mode it prevents is the one where a user sets up
a paid key for a one-off experiment, forgets about it, and runs
`ssm-transcriber transcribe big-file.mp4` a month later expecting a free run
and gets a $12 bill instead.

**Where it shows up:** `docs/PLAN.md` Phase 1 Foundations F4 and Phase 5
(budget router) and Phase 6a (paid LLM fallback).

---

## Vibe coding

The practice of building software primarily through natural language
conversation with AI coding tools, where the developer's job shifts from
writing code to **directing, reviewing, and verifying** AI-generated code.
The developer sets architectural intent and constraints; the AI produces
the implementation; the developer reviews, tests, and course-corrects.

**Why it matters here.** SSM-Transcriber is built with five AI tools in
rotation (Claude Code, Codex, Gemini CLI, Cursor, Copilot). The context
file strategy, the teaching register, and the plan-review-before-code
workflow are all infrastructure for making vibe coding produce correct
code faster. The project is as much an experiment in *how to direct AI
tools* as it is a transcription pipeline.

**Where it shows up:** every file in this repo was written or reviewed with
AI assistance. Patterns and lessons in
[`vibe-coding-notes.md`](vibe-coding-notes.md).

---

## VAD (Voice Activity Detection)

A signal-processing step that scans an audio stream and returns the time
ranges that contain speech (vs. silence, music, or noise). In this project,
VAD is a **sidecar**, not a transform (F3/F5 rationale): the canonical
transcription always runs on the full, unmodified audio so that segment
timestamps match the original media timeline. The VAD output is stored as
a separate list of `(start, end)` pairs and is used only for (a) estimating
`speech_duration` for cost display, and (b) building a reduced upload when
routing to a cloud provider.

**Why the sidecar distinction matters.** If you strip silence before
transcribing, your SRT captions drift by however much silence was removed.
This bug ships, then a user notices their subtitles are 11 seconds out of
sync, and three hours later someone figures out it was the VAD filter. The
sidecar design makes that impossible by construction.

**Where it shows up:** `docs/PLAN.md` cost-saving item 3 (rewritten in PR #3)
and Phase 1 Foundations F7 test fixtures (`short_speech_with_silence.wav`
exists specifically to verify timestamp fidelity).
