# SSM-Transcriber — Claude Code Context

Start here:
- [`docs/ai/README.md`](docs/ai/README.md) — AI-agnostic operator guide
- [`docs/PLAN.md`](docs/PLAN.md) — detailed roadmap and F1–F8 contracts
- [`docs/learn/README.md`](docs/learn/README.md) — living-doc and teaching-register rules

## Project

Local-first audio/video transcription pipeline. Default path is local
`faster-whisper` (`$0` after model download); cloud transcription and paid LLM
features are opt-in.

## Run commands

```bash
uv sync
uv run ssm-transcriber --help
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/ tests/
```

## Current phase

Phase 0 skeleton only. `src/transcriber/cli.py` and `src/transcriber/config.py`
exist; core pipeline, sources, formatters, providers, and agents are not built
yet.

## Guardrails to keep inline

- Keep the core sync through Phase 4; do not add `async def` to pipeline,
  source, provider, or formatter code.
- Config access is `from transcriber.config import settings`; never read
  `os.environ` directly.
- Do not cache on `SHA256(file + quality)`; F3 requires a versioned composite key.
- Default budget is `free`; cloud calls require the two-gate spend model and
  explicit cost confirmation.
- `RunWorkspace` owns temp artifacts; output writes must be atomic in the
  destination directory.
- VAD is a sidecar only; do not strip canonical audio before transcription.
- No `print()` in library code, and never dump full settings/secrets to logs or
  user-facing output.

## Claude-specific workflow

- High-value slash commands live in `.claude/commands/`:
  `/review`, `/ship`, `/new-pr`, `/phase-check`
- Use them for workflow-heavy tasks. Do not add generic launchers unless they
  enforce repo-specific inputs, outputs, and checks.
- When changing docs, follow the source docs instead of inventing new policy in
  command files or tool adapters.
