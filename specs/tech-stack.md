# Tech Stack

> Layer / Choice / Rationale for the engineering decisions that bind future
> code. F1–F8 are the binding contracts in [`docs/PLAN.md`](../docs/PLAN.md);
> only their names appear here. For contract bodies, follow the links.

## Runtime and packaging

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 (pinned `>=3.12,<3.13`) | Type hints stable, `match` and PEP-695 generics available; pinned to avoid 3.13 instability. See [`pyproject.toml`](../pyproject.toml). |
| Package manager | `uv` | Fast, reproducible lockfile (`uv.lock` committed). One command for sync, run, add. |
| CLI | `typer` + `rich` | Type-driven argument parsing; `rich` for confirmation prompts and progress UI. |
| Settings | `pydantic-settings` | Env-aware, `.env`-aware, validates types at load. See [`config.py`](../src/transcriber/config.py). |

## Pipeline shape

| Layer | Choice | Rationale |
|---|---|---|
| Concurrency model | **Sync through Phase 4**; revisit at Phase 5 only if needed | Avoids `async` complexity for sequential I/O. See [`docs/PLAN.md`](../docs/PLAN.md) §F1. |
| Source contract | `PreparedMedia` (F2) | Every source returns the same dataclass; pipeline is source-agnostic. See [`docs/PLAN.md`](../docs/PLAN.md) §F2. |
| Cache key | Versioned composite (F3) | `audio_sha256 + provider_id + model_id + revision + language + vad_mode + schema_version`. Never `SHA256(file + quality)`. See [`docs/PLAN.md`](../docs/PLAN.md) §F3. |
| Spend gating | Two-gate model (F4) | Gate 1 = configured key; Gate 2 = `--budget` permits paid use. Default `--budget free` blocks all paid providers. See [`docs/PLAN.md`](../docs/PLAN.md) §F4. |
| Temp lifecycle | `RunWorkspace` (F5) | One temp dir per CLI invocation; atomic output writes via `.tmp` + `os.replace()`. See [`docs/PLAN.md`](../docs/PLAN.md) §F5. |
| VAD | Sidecar only | Used for cost estimation and reduced uploads; canonical audio is never stripped before transcription. |

## Transcription providers

| Layer | Choice | Rationale |
|---|---|---|
| Local default | `faster-whisper` | `$0` default; runs on the user's machine; no API key needed. |
| Cloud — fixed-price | Deepgram, AssemblyAI, OpenAI Whisper | Provider abstraction (Phase 5) lets the user opt in via `--budget low\|best`. See [`docs/PLAN.md`](../docs/PLAN.md) §Phase 5. |
| Cloud — experimental | Hugging Face Inference Providers | Later, explicit-only; not an automatic routing candidate. |
| Retry | `tenacity` (3 attempts, exp backoff on 429/503/timeout, never 4xx) | Standard wrapper for cloud calls. |

## Output

| Layer | Choice | Rationale |
|---|---|---|
| Formats | txt, srt, md, json (Phase 3) | Markdown frontmatter is general-purpose YAML so output works in Obsidian, NotebookLM, and paste-into-AI workflows without lock-in. |
| Atomicity | Write `<output>.tmp` in destination dir, then `os.replace()` | Crash-safe; never leaves a half-written file. |

## LLM (Phase 6a+)

| Layer | Choice | Rationale |
|---|---|---|
| Abstraction | `litellm` | Cloud-agnostic; one API for Groq / Gemini / Anthropic / OpenAI. |
| Fallback chain | Groq (free) → Gemini Flash → Claude Haiku → configured override | Cheapest-first; paid LLMs require `--allow-paid-llm` plus cost confirmation. |
| Caching | Anthropic prompt caching enabled when reachable | Reduces repeated-system-prompt cost. |

## Agents (Phase 6b)

| Layer | Choice | Rationale |
|---|---|---|
| Orchestration | LangGraph | Graph boundary for multi-agent flows; deferred until Phase 6b. |

## Quality gates

| Layer | Choice | Rationale |
|---|---|---|
| Lint | `ruff` (selects E, F, I, UP, B; line length 100) | See [`pyproject.toml`](../pyproject.toml). |
| Type check | `mypy` (`python_version = "3.12"`, `mypy_path = "src"`) | Enforces F1–F8 contract shapes. |
| Test runner | `pytest` (`asyncio_mode = "auto"`) | CI runs `ruff` + `mypy` + `pytest` on every PR. |
| Real-API tests | Manual runbooks in `tests/manual/` | Real cloud calls stay out of CI to avoid bill leaks. |

## Guardrails

These are repo policy from [`CLAUDE.md`](../CLAUDE.md); violations are review
blockers.

- Use `from transcriber.config import settings`; never read `os.environ`
  directly outside `config.py`.
- No `print()` in library code; use `logging`. `rich` is for CLI presentation
  only.
- Never log full settings or secrets.
- Cache keys are versioned composites (F3) — never `SHA256(file + quality)`.
- Default budget is `free`; any cloud call passes the two-gate spend check
  with explicit cost confirmation.
- VAD is a sidecar only — never strip canonical audio before transcription.
- `RunWorkspace` owns temp artifacts; output writes are atomic in the
  destination directory.
