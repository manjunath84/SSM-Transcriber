# Transciber — Claude Code Context

## What this project does
Multi-agent audio/video transcription pipeline. Transcribes from local files, YouTube URLs,
and Google Drive. Local-first (zero cost by default), cloud providers are opt-in.

## Running the project
```bash
uv sync                          # install dependencies
uv run transciber --help         # show CLI commands
uv run transciber transcribe ./video.mp4
uv run pytest                    # run tests
uv run ruff check src/           # lint
uv run mypy src/                 # type check
```

## Current phase: 0 — Skeleton
Implemented: pyproject.toml, CLI stub, config files.
Not yet implemented: audio extraction, transcription, sources, formatters.

## Architecture (implemented phase by phase)
- **Phase 1**: `src/transciber/core/` — audio_extractor, transcriber, cache
- **Phase 2**: `src/transciber/sources/` — local, youtube
- **Phase 3**: `src/transciber/formatters/` — txt, srt, md, json
- **Phase 4**: `src/transciber/sources/google_drive.py`
- **Phase 5**: `src/transciber/providers/` — abstraction + cloud engines
- **Phase 6**: `src/transciber/agents/` — LangGraph multi-agent

## Key conventions
- All I/O operations are `async`; only `asyncio.run()` at the CLI boundary
- Config via `pydantic-settings` in `src/transciber/config.py` — never `os.environ` directly
- No hardcoded provider names outside registry + settings validator
- Cache key = SHA256(file content + quality setting) — avoids re-transcribing same file
- VAD silence stripping always on — reduces billable duration if cloud provider used
- Cloud calls always show estimated cost and prompt confirmation before proceeding

## Cost model (never break this)
- Default run = $0 (local faster-whisper)
- `--summarize` / `--clean` flags are opt-in (LLM not invoked otherwise)
- `--budget free` rejects any cloud call
- Cloud cost is always estimated and confirmed before any API call

## Adding a new transcription provider (Phase 5+)
1. Create `src/transciber/providers/<name>.py` implementing `TranscriptionProviderBase`
2. Add `cost_per_minute: float` class attribute
3. Register in `src/transciber/providers/__init__.py` registry dict
4. Add API key to `TranscriberSettings` and `.env.example`

## Adding a new media source
1. Create `src/transciber/sources/<name>.py` implementing `MediaSourceBase`
2. Implement `can_handle(uri: str) -> bool`
3. Register in `src/transciber/sources/__init__.py` — `resolve_source()` checks in order
