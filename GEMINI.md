# SSM-Transcriber — Gemini CLI Context

> **Roadmap:** See [`docs/PLAN.md`](docs/PLAN.md) for the full phased
> implementation plan.

## What this project does
Transcribes audio and video from local files, YouTube URLs, and Google Drive.
Uses `faster-whisper` locally by default (free, no API keys). Cloud transcription
providers (Deepgram, AssemblyAI) are opt-in via env vars.

## Why these technology choices
- `uv` instead of pip/poetry: 10-100x faster, 2025 Python standard
- `faster-whisper` instead of openai-whisper: 3-5x faster, same accuracy, runs offline
- `litellm` for LLM calls: swap providers without code changes
- `langgraph` for multi-agent (Phase 6+): explicit state machine, easy to add Notes Agent
- Local-first philosophy: default run costs $0, cloud is always opt-in

## Running the project
```bash
uv sync
uv run ssm-transcriber transcribe ./video.mp4
uv run ssm-transcriber transcribe "https://youtu.be/..."
uv run ssm-transcriber --help
```

## Current phase: 0 — Skeleton
CLI stub exists. Audio extraction and transcription not yet implemented (Phase 1).

## Key entry points
- CLI: `src/transcriber/cli.py` → `app` (typer)
- Config: `src/transcriber/config.py` → `settings` singleton (pydantic-settings)
- Core pipeline (Phase 1+): `src/transcriber/core/`

## Cost rules (never violate)
1. Default: local faster-whisper only, $0
2. Cloud providers: only when `TRANSCRIBER_TRANSCRIPTION_PROVIDER` env var is set to a non-local value
3. Always show estimated cost + confirm before any cloud API call
4. LLM: only invoked with `--summarize` or `--clean` flag

## Google Drive (Phase 4)
Uses `google-api-python-client`. Auth: `transcriber auth google-drive` → OAuth2 → saves token.
URI format: `drive://FILE_ID`
