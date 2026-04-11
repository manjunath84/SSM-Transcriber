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

## Cost rules (never violate — see `docs/PLAN.md` § Phase 1 Foundations F4)
1. Default: local faster-whisper only, $0
2. **Two-gate spend model:** "API key configured" does not mean "provider will be used." `--budget free` (the default) rejects any paid provider even if its key is set. A paid provider is only used when both the key is configured *and* the budget allows it.
3. Always show estimated cost (from VAD `speech_duration`, not total media duration) + require confirmation before any cloud API call. `--yes` skips the prompt but still honors the budget.
4. LLM: `--summarize` / `--clean` default to the free Groq tier. Falling back to any paid LLM (Gemini, Claude, OpenAI) requires `--allow-paid-llm` + cost confirmation — no silent escalation.
5. Cache keys are **versioned composites** (F3), not raw file hashes — changing the model, language, or VAD mode must produce a different key.

## Core conventions (binding)
- **Sync through Phase 4.** No `async def` on pipeline, source, provider, or formatter methods. Revisit at Phase 5 only if real concurrency appears. (F1)
- Sources return `PreparedMedia` (F2); the pipeline never sees raw URIs.
- Every CLI invocation uses one `RunWorkspace` with `try/finally` cleanup and atomic output writes via `os.replace()`. (F5)
- VAD is a **sidecar**, not a transform of the canonical audio — segment timestamps always match the original media timeline.
- Never log secrets; use `settings.redacted_dump()` for any diagnostic output.

## Google Drive (Phase 4)
Uses `google-api-python-client`. Auth: `transcriber auth google-drive` → OAuth2 → saves token.
URI format: `drive://FILE_ID`
