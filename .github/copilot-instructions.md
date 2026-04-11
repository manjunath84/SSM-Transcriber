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
2. Implement `def transcribe(audio_path, language, diarize) -> TranscriptionResult` — **sync, not async** (Phase 1 Foundations F1)
3. Set `cost_per_minute: float = X.XX` and `provider_id: str` as class attributes
4. Expose `model_id` and `model_revision` — both are required inputs to the cache key (F3)
5. Register: add to `_REGISTRY` dict in `src/transcriber/providers/__init__.py`

### Adding a media source
1. Subclass `MediaSourceBase` in `src/transcriber/sources/base.py`
2. Implement `can_handle(uri: str) -> bool` (match by hostname for URL sources, not scheme) and `def prepare(uri, workspace) -> PreparedMedia` — **sync**
3. Source must write any downloaded artifacts into the `RunWorkspace`, never into its own `tempfile.mkdtemp` (F5)
4. Register in `src/transcriber/sources/__init__.py` — `resolve_source()` iterates in order

### Error handling in CLI
```python
# Use typer.Exit(code=1) for user-facing errors, not bare raise.
# For output, use the module-level `console = Console()` from src/transcriber/cli.py
# For structured logging, use `logging.getLogger(__name__)` — never print() inside library code (F8).
```

## What NOT to do
- Do not use `print()` — use `rich.console.Console` in the CLI layer, `logging` everywhere else
- Do not call cloud APIs without the two-gate check: key configured AND budget allows (F4)
- Do not hardcode provider strings ("deepgram", "assemblyai") outside the registry
- **Do not add `async def`** to pipeline, source, provider, or formatter methods through Phase 4 — the core is sync (F1)
- Do not cache transcripts on `SHA256(file + quality)` — use the versioned composite key (F3)
- Do not strip silence from the canonical audio — VAD is a sidecar only
- Do not log `settings.model_dump()`; use `settings.redacted_dump()` (F8)

## Current phase: 0 — Skeleton
Core transcription (`core/`), sources (`sources/`), formatters (`formatters/`),
providers (`providers/`), and agents (`agents/`) are not yet implemented.
