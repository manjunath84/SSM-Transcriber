# SSM-Transcriber — Gemini CLI Context

Read:
- [`docs/ai/README.md`](docs/ai/README.md)
- [`docs/PLAN.md`](docs/PLAN.md)
- [`docs/learn/README.md`](docs/learn/README.md) when touching PR/docs workflow

## Project

Audio/video transcription from local files first; YouTube, Google Drive, cloud
providers, and LangGraph arrive in later phases.

## Run commands

```bash
uv sync
uv run ssm-transcriber --help
uv run pytest
```

## Current phase

Phase 0 skeleton. Only the CLI stub and config singleton are implemented.

## Inline guardrails

- Keep the core sync through Phase 4; do not add `async def` to pipeline,
  source, provider, or formatter code.
- Use `from transcriber.config import settings`; never read `os.environ`
  directly.
- Cache keys are versioned composites; never cache on `SHA256(file + quality)`.
- Default budget is `free`; any cloud call must pass the two-gate spend check
  and show cost confirmation.
- `RunWorkspace` owns temp artifacts; output writes must be atomic in the
  destination directory.
- VAD is a sidecar only; do not strip canonical audio before transcription.
- No `print()` in library code; never dump full settings or secrets to logs or
  user-facing output.
- Living docs update only when the concept exists and can cite a real repo
  location.
