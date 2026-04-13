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

- Keep the core sync through Phase 4
- No direct `os.environ`
- Default spend path is `$0`; two-gate spend model applies to all cloud calls
- Cache keys are versioned composites, not raw file hashes
- VAD is a sidecar only
- No speculative living-doc entries
