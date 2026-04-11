# SSM-Transcriber — Claude Code Context

> **Full roadmap:** [`docs/PLAN.md`](docs/PLAN.md) — phased implementation
> plan, cost optimization strategy, per-phase verification. Read it when
> you need context on *why* the project is structured this way or *what*
> comes next.

## What this project does
Multi-agent audio/video transcription pipeline. Transcribes from local files, YouTube URLs,
and Google Drive. Local-first (zero cost by default), cloud providers are opt-in.

## Running the project
```bash
uv sync                          # install dependencies
uv run ssm-transcriber --help         # show CLI commands
uv run ssm-transcriber transcribe ./video.mp4
uv run pytest                    # run tests
uv run ruff check src/           # lint
uv run mypy src/                 # type check
```

## Current phase: 0 — Skeleton
Implemented: pyproject.toml, CLI stub, config files.
Not yet implemented: audio extraction, transcription, sources, formatters.

## Architecture (implemented phase by phase)
- **Phase 1**: `src/transcriber/core/` — audio_extractor, transcriber, cache
- **Phase 2**: `src/transcriber/sources/` — local, youtube
- **Phase 3**: `src/transcriber/formatters/` — txt, srt, md, json
- **Phase 4**: `src/transcriber/sources/google_drive.py`
- **Phase 5**: `src/transcriber/providers/` — abstraction + cloud engines
- **Phase 6**: `src/transcriber/agents/` — LangGraph multi-agent

## Key conventions
- **Sync, not async, through Phase 4.** Every library in the stack is blocking-native; do not introduce `async def` on pipeline, source, provider, or formatter methods. Revisit at Phase 5 only if a real concurrency need appears. (Phase 1 Foundations F1)
- Config via `pydantic-settings` in `src/transcriber/config.py` — never `os.environ` directly
- No hardcoded provider names outside registry + settings validator
- Never log secrets. Use `settings.redacted_dump()` for any diagnostic output; never `settings.model_dump()` in user-facing commands (F8)

## Phase 1 Foundations (binding contracts — see `docs/PLAN.md`)
These are the contracts all later phases build on. If you are implementing Phase 1, read the full section in `docs/PLAN.md` first.
- **F2 `PreparedMedia`** — sources return this dataclass; the pipeline never sees raw URIs
- **F3 Versioned cache key** — composite of audio hash + provider id + model id + model revision + language + VAD mode + pipeline schema version. Never cache on "file + quality" alone
- **F4 Two-gate spend model** — "key configured" ≠ "provider allowed". `--budget free` rejects any paid provider even if its key is set. Paid LLM fallback requires `--allow-paid-llm` + cost confirmation
- **F5 `RunWorkspace`** — one per CLI invocation, `try/finally` cleanup, atomic output writes via `os.replace()`
- **F6 Model download preflight** — first-run `faster-whisper` downloads are surfaced, not silent. `ssm-transcriber models download` prefetches
- **F7 Fixtures and stubs** — fixtures in `tests/fixtures/`, adapter stubs in `tests/stubs/`, integration tests gated on `SSM_INTEGRATION=1`
- **VAD is a sidecar, not a transform** — the canonical transcript runs on full audio so timestamps are truthful. VAD regions are used only for cost display and reduced cloud uploads

## Cost model (never break this)
- Default run = $0 (local faster-whisper)
- `--summarize` / `--clean` default to the free Groq tier; paid LLM fallback requires `--allow-paid-llm` + confirmation (no silent escalation)
- `--budget free` rejects any paid provider regardless of which keys are configured
- Cloud cost is always estimated (from `speech_duration`, not total duration) and confirmed before any API call

## Adding a new transcription provider (Phase 5+)
1. Create `src/transcriber/providers/<name>.py` implementing `TranscriptionProviderBase`
2. Add `cost_per_minute: float` class attribute
3. Register in `src/transcriber/providers/__init__.py` registry dict
4. Add API key to `TranscriberSettings` and `.env.example`

## Adding a new media source
1. Create `src/transcriber/sources/<name>.py` implementing `MediaSourceBase`
2. Implement `can_handle(uri: str) -> bool`
3. Register in `src/transcriber/sources/__init__.py` — `resolve_source()` checks in order

## Author context — teaching register and interview prep
Primary author is a senior Java developer transitioning to AI/ML engineering. Learning artifacts live in [`docs/learn/`](docs/learn/README.md). On every PR, apply these rules:
- **Teaching register by default.** Explain the *why*; give a Java analogue when a Python/AI concept first appears.
- **Update living docs in the same PR.** Idioms → [`python-notes.md`](docs/learn/python-notes.md). AI/ML terms → [`glossary.md`](docs/learn/glossary.md). PR explainer → `docs/learn/prs/pr-NNN-<slug>.md`.
- **Cite real files.** Broken pointers in learning docs block review. Full conventions: [`docs/learn/README.md`](docs/learn/README.md). Teaching register does not override `docs/PLAN.md` F1–F8.
