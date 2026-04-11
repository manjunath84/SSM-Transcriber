# GitHub Copilot Instructions — SSM-Transcriber

> **Roadmap:** See [`docs/PLAN.md`](../docs/PLAN.md) for the phased
> implementation plan and cost strategy.

## Project overview
Python transcription pipeline. Transcribes audio/video from local files, YouTube, or Google Drive.
Provider-agnostic: transcription engine, LLM, and media source are all swappable via env vars.

## Key patterns

### Config access
```python
from transcriber.config import settings
# Use settings.whisper_model_size, settings.transcription_provider, etc.
# Never read os.environ directly.
```

### Adding a transcription provider (Phase 5+)
1. Subclass `TranscriptionProviderBase` in `src/transcriber/providers/base.py`
2. Implement `async def transcribe(audio_path, language, diarize) -> TranscriptionResult`
3. Set `cost_per_minute: float = X.XX` as a class attribute
4. Register: add to `_REGISTRY` dict in `src/transcriber/providers/__init__.py`

### Adding a media source
1. Subclass `MediaSourceBase` in `src/transcriber/sources/base.py`
2. Implement `can_handle(uri: str) -> bool` and `async def fetch(uri, dest_dir) -> Path`
3. Register in `src/transcriber/sources/__init__.py` — `resolve_source()` iterates in order

### Error handling in CLI
```python
# Use typer.Exit(code=1) for user-facing errors, not bare raise.
# For output, use the module-level `console = Console()` from src/transcriber/cli.py
# (logger module will be added when needed — Phase 1+).
```

## What NOT to do
- Do not use `print()` — use `rich.console.Console`
- Do not call cloud APIs without showing estimated cost first
- Do not hardcode provider strings ("deepgram", "assemblyai") outside the registry
- Do not add `asyncio.run()` inside library code — only in `cli.py`

## Current phase: 0 — Skeleton
Core transcription (`core/`), sources (`sources/`), formatters (`formatters/`),
providers (`providers/`), and agents (`agents/`) are not yet implemented.
