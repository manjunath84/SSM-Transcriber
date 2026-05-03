# SSM-Transcriber — Claude Code Context

Start here:
- [`specs/`](specs/) — SDD constitution (mission, tech-stack, roadmap) and per-feature specs
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

Phase 0 skeleton only. Only the CLI stub (`cli.py`) and config singleton
(`config.py`) are implemented; core pipeline, sources, formatters, providers,
and agents are not built yet.

## Guardrails to keep inline

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
- Vendor API calls (request shape, field names, model identifiers) must be
  copied verbatim from a working call recorded in the feature spec's
  `## Reference calls (verbatim)` section, or from a fresh ctx7 docs fetch
  with the retrieval date captured. Never paraphrase from memory or
  training data — vendor APIs change, and PR #12 caught three wrong-shape
  bugs in one run for exactly this reason.
- HTTP mocks (`responses` library) must include body-shape matchers
  (`responses.matchers.json_params_matcher` or equivalent) for any test
  that exercises the request payload. URL+method-only matching lets
  wrong-field-name regressions through; see PR #12's
  `test_create_transcript_body_uses_plural_speech_models` as the
  exemplar.

## Claude-specific workflow

- High-value slash commands live in `.claude/commands/`:
  `/review`, `/ship`, `/new-pr`, `/phase-check`
- Use them for workflow-heavy tasks. Do not add generic launchers unless they
  enforce repo-specific inputs, outputs, and checks.
- When changing docs, follow the source docs instead of inventing new policy in
  command files or tool adapters.
