# SSM-Transcriber — Claude Code Context

Start here:
- [`specs/`](specs/) — SDD constitution (mission, tech-stack, roadmap) and per-feature specs
- [`docs/ai/README.md`](docs/ai/README.md) — AI-agnostic operator guide
- [`docs/PLAN.md`](docs/PLAN.md) — detailed roadmap and F1–F8 contracts
- [`docs/learn/README.md`](docs/learn/README.md) — living-doc and teaching-register rules
- [Project board](https://github.com/users/manjunath84/projects/3) — live status of phases/slices ([`docs/ai/runbooks/tracking.md`](docs/ai/runbooks/tracking.md) for the convention)

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

Phase 0–1 + Phase 4 (Slices 2 + 2.5) shipped: CLI, config, sources
(local, Drive URL passthrough), AssemblyAI provider, markdown
formatter, Drive upload destination. Phases 2 (YouTube), 3 (LLM
post-processing), 5 (multi-provider), 6 (multi-agent) are open on the
[Project board](https://github.com/users/manjunath84/projects/3).
Phase 4 Slice 3 (Drive OAuth + private files) is deferred until a
concrete private-file use case lands. See `docs/PLAN.md` for the full
roadmap and live board for execution status.

## Guardrails to keep inline

- Library code (`sources/`, `providers/`, `formatters/`, `destinations/`,
  `core/`) stays sync; never add `async def` there. Orchestration MAY be
  event-driven (Step Functions, browser polling) at the hosting boundary
  only (`src/transcriber/hosted/`). See PLAN.md §F1.
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
  copied byte-for-byte from a working call pasted into the feature spec's
  `## Reference calls (verbatim)` section, or from a ctx7 docs fetch
  performed within the current PR (retrieval date captured in that section
  too). Never paraphrase from memory or training data — vendor APIs change,
  and PR #12 caught two wrong-shape bugs (and one unrelated `.env`-loading
  bug) in one run for exactly this reason.
- HTTP mocks (`responses` library) must use
  `responses.matchers.json_params_matcher` (or the equivalent body-content
  matcher for non-JSON payloads) on every mock whose corresponding
  production code constructs a request body. URL+method-only matching
  lets wrong-field-name regressions through unnoticed — exactly what hid
  PR #12's `speech_model` → `speech_models` regression past 41 unit tests.

## Claude-specific workflow

- High-value slash commands live in `.claude/commands/`:
  `/review`, `/ship`, `/new-pr`, `/phase-check`
- Use them for workflow-heavy tasks. Do not add generic launchers unless they
  enforce repo-specific inputs, outputs, and checks.
- When changing docs, follow the source docs instead of inventing new policy in
  command files or tool adapters.
- Work is tracked on the [SSM-Transcriber Roadmap Project](https://github.com/users/manjunath84/projects/3).
  Granularity: one issue per PLAN.md phase/slice. PR bodies use
  `Closes #<issue>` so merges auto-close the board card. Full
  convention: [`docs/ai/runbooks/tracking.md`](docs/ai/runbooks/tracking.md).
  Do **not** open issues per PR or per file — those land in commits/PR
  descriptions, not the board.
