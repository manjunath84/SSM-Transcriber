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

Phase 0 skeleton only. `cli.py` and `config.py` exist; downstream pipeline
modules are still planned.

## Non-negotiable inline rules

- No `async def` on pipeline, source, provider, or formatter code through Phase 4
- Use `from transcriber.config import settings`, never `os.environ`
- No transcript cache keyed on file hash + quality alone
- Default budget is `free`; paid providers require both configured keys and an
  allowed budget
- No `print()` in library code; do not dump full settings or secrets
- Living docs update only when the concept exists and can cite a real repo location
