# Journey

> Running narrative of what was built in SSM-Transcriber and *why*, written in
> teaching register. **Newest first.** Each merged PR gets one entry. This is
> the companion to the commit history — `git log` tells you *what*, this file
> tells you *why it mattered and what you should take away from it*.
>
> If you're reading this for the first time, scroll to the bottom and read
> forward. If you're catching up, read top-down.

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
- Five AI context files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`,
  `.github/copilot-instructions.md`) so any AI tool the author uses —
  Claude Code, Codex, Gemini CLI, Cursor, Copilot — reads the same rules and
  writes code that matches the project's conventions. This is a
  **deliberately redundant** design: each tool reads its own file, so
  updating them all in lockstep is a small tax on every PR in exchange for
  "my AI tools all give the same answer."

The PR ended in a stubbed `uv run ssm-transcriber --help` that prints the
command tree but refuses to actually transcribe anything. That's Phase 0's
success criterion — the scaffolding exists, the CI is green, and Phase 1 has
a clean runway.

The thing this PR is *most* useful for as a learning artifact is: it's a
snapshot of a modern (2025) Python project starter kit. If you want to build
another Python CLI from scratch, clone Phase 0 and delete the transcribe
command.
