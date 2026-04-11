# Transciber — Agent Instructions

## Project
Multi-agent audio/video transcription pipeline. Python 3.11+, managed with `uv`.

## Stack
- Transcription: `faster-whisper` (local, free) + Deepgram / AssemblyAI / OpenAI (cloud, opt-in)
- LLM: `litellm` (cloud-agnostic — Groq → Gemini → Claude by cost)
- Agents: `langgraph` (Phase 6+)
- CLI: `typer` + `rich`
- Config: `pydantic-settings`

## Commands
```bash
uv sync                          # install deps
uv run transciber --help
uv run transciber transcribe ./video.mp4
uv run pytest
uv run ruff check src/
```

## Current phase: 0 — Skeleton
Only the CLI stub and config files exist. Transcription not yet implemented.

## Pipeline (when fully built)
```
URI input
  → resolve_source(uri)          # local | youtube | google_drive
  → source.fetch() → audio WAV
  → cache.get(hash) or transcriber.transcribe()
  → formatter.format(result)
  → output file
```

## File layout
```
src/transciber/
  cli.py               # typer entry point
  config.py            # pydantic-settings singleton
  core/                # audio_extractor, transcriber, cache   [Phase 1]
  sources/             # local, youtube, google_drive          [Phase 2-4]
  formatters/          # txt, srt, md, json                    [Phase 3]
  providers/           # provider ABC + cloud engines          [Phase 5]
  agents/              # LangGraph state + graph               [Phase 6]
```

## Rules
- Never read `os.environ` directly — use `from transciber.config import settings`
- All provider methods are async; nodes return `dict` of state updates
- Cache every transcription result by SHA256(content + quality)
- Before any cloud API call: compute and display estimated cost, require confirmation
- Default budget is `free` — local only, zero spend
