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
- All I/O operations are `async`; only `asyncio.run()` at the CLI boundary
- Config via `pydantic-settings` in `src/transcriber/config.py` — never `os.environ` directly
- No hardcoded provider names outside registry + settings validator

## Conventions that will land in later phases (don't assume they exist yet)
- **Phase 1**: transcript cache keyed by SHA256(file + quality); VAD silence stripping
- **Phase 5**: cloud calls show estimated cost and prompt confirmation before proceeding
- **Phase 6a**: LLM post-processing via `litellm` (cheapest-first fallback)

## Cost model (never break this)
- Default run = $0 (local faster-whisper)
- `--summarize` / `--clean` flags are opt-in (LLM not invoked otherwise)
- `--budget free` rejects any cloud call
- Cloud cost is always estimated and confirmed before any API call

## Adding a new transcription provider (Phase 5+)
1. Create `src/transcriber/providers/<name>.py` implementing `TranscriptionProviderBase`
2. Add `cost_per_minute: float` class attribute
3. Register in `src/transcriber/providers/__init__.py` registry dict
4. Add API key to `TranscriberSettings` and `.env.example`

## Adding a new media source
1. Create `src/transcriber/sources/<name>.py` implementing `MediaSourceBase`
2. Implement `can_handle(uri: str) -> bool`
3. Register in `src/transcriber/sources/__init__.py` — `resolve_source()` checks in order
