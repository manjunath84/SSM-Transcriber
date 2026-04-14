# SSM-Transcriber — Agent Instructions

Primary references:
- [`docs/ai/README.md`](docs/ai/README.md) — workflow routing and command inventory
- [`docs/PLAN.md`](docs/PLAN.md) — detailed technical contracts
- [`docs/learn/README.md`](docs/learn/README.md) — PR explainer and living-doc rules

## Project

Python 3.12 transcription pipeline managed with `uv`. Local-first by default;
cloud providers and LLM cleanup/summarization are opt-in.

## Run commands

```bash
uv sync
uv run ssm-transcriber --help
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/ tests/
```

## Current phase

Phase 0 skeleton only. Only the CLI stub (`cli.py`) and config singleton
(`config.py`) are implemented; downstream pipeline modules are still planned.

## Non-negotiable inline rules

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
