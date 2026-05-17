# Tech Stack

> Layer / Choice / Rationale for the engineering decisions that bind future
> code. For the canonical human-readable stack list, see
> [`README.md`](../README.md#stack). The tables below record the *decisions*
> (rationale and trade-offs) behind each choice, not just the names.
> F1–F8 are the binding contracts in [`docs/PLAN.md`](../docs/PLAN.md);
> only their names appear here. For contract bodies, follow the links.

## Runtime and packaging (current — in `pyproject.toml`)

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 (pinned `>=3.12,<3.13`) | Type hints stable, `match` and PEP-695 generics available; pinned to avoid 3.13 instability. See [`pyproject.toml`](../pyproject.toml). |
| Package manager | `uv` | Fast, reproducible lockfile (`uv.lock` committed). One command for sync, run, add. |
| CLI | `typer` + `rich` | Type-driven argument parsing; `rich` for confirmation prompts and progress UI. |
| Settings | `pydantic-settings` | Env-aware, `.env`-aware, validates types at load. See [`config.py`](../src/transcriber/config.py). |

## Pipeline shape (planned — Phase 1+; not yet implemented)

| Layer | Choice | Rationale |
|---|---|---|
| Concurrency model | **Sync through Phase 4**; revisit at Phase 5 only if needed | Avoids `async` complexity for sequential I/O. See [`docs/PLAN.md`](../docs/PLAN.md) §F1. |
| Source contract | `PreparedMedia` (F2) | Every source returns the same dataclass; pipeline is source-agnostic. See [`docs/PLAN.md`](../docs/PLAN.md) §F2. |
| Cache key | Versioned composite (F3) | `audio_sha256 + provider_id + model_id + revision + language + vad_mode + schema_version`. Never `SHA256(file + quality)`. See [`docs/PLAN.md`](../docs/PLAN.md) §F3. |
| Spend gating | Two-gate model (F4) | Gate 1 = configured key; Gate 2 = `--budget` permits paid use. Default `--budget free` blocks all paid providers. See [`docs/PLAN.md`](../docs/PLAN.md) §F4. |
| Temp lifecycle | `RunWorkspace` (F5) | One temp dir per CLI invocation; atomic output writes via `.tmp` + `os.replace()`. See [`docs/PLAN.md`](../docs/PLAN.md) §F5. |
| VAD | Sidecar only | Used for cost estimation and reduced uploads; canonical audio is never stripped before transcription. |

## Transcription providers (planned — `faster-whisper` Phase 1; cloud Phase 5)

| Layer | Choice | Rationale |
|---|---|---|
| Local default | `faster-whisper` (Phase 1) | `$0` default; runs on the user's machine; no API key needed. |
| Cloud — fixed-price | Deepgram, AssemblyAI, OpenAI Whisper (Phase 5) | Provider abstraction lets the user opt in via `--budget low\|best`. See [`docs/PLAN.md`](../docs/PLAN.md) §Phase 5. |
| Cloud — experimental | Hugging Face Inference Providers (later) | Explicit-only; not an automatic routing candidate. |
| Retry | `tenacity` (Phase 5) | 3 attempts, exp backoff on 429/503/timeout, never on other 4xx. Standard wrapper for cloud calls. |

## Output (planned — Phase 3+; not yet implemented)

| Layer | Choice | Rationale |
|---|---|---|
| Formats | txt, srt, md, json | Markdown frontmatter is general-purpose YAML so output works in Obsidian, NotebookLM, and paste-into-AI workflows without lock-in. |
| Atomicity | Write `<output>.tmp` in destination dir, then `os.replace()` | Crash-safe; never leaves a half-written file. |

## LLM (planned — Phase 6a+; not yet implemented)

| Layer | Choice | Rationale |
|---|---|---|
| Abstraction | `litellm` | Cloud-agnostic; one API for Groq / Gemini / Anthropic / OpenAI. |
| Fallback chain | Groq (free) → Gemini Flash → Claude Haiku → configured override | Cheapest-first; paid LLMs require `--allow-paid-llm` plus cost confirmation. |
| Caching | Anthropic prompt caching enabled when reachable | Reduces repeated-system-prompt cost. |

## Agents (planned — Phase 6b+; not yet implemented)

| Layer | Choice | Rationale |
|---|---|---|
| Orchestration | LangGraph | Graph boundary for multi-agent flows. |

## AWS deployment (Phase 7 hosted UI)

> The hosted multi-user surface only; the local CLI has no AWS dependency.
> See [`specs/2026-05-14-hosted-ui/requirements.md`](2026-05-14-hosted-ui/requirements.md).
> **Scope note:** Phase 7a (auth + viewer) provisions Cognito (+Google IdP), S3, CloudFront, API Gateway HTTP API, Lambda, and DynamoDB. Step Functions, SES, and EventBridge are part of the full Phase 7 surface and land in later slices (7b/7c).

| Layer | Choice | Rationale |
|---|---|---|
| Compute | AWS Lambda | Serverless, scale-to-zero so a dormant stack costs ~$0; the sync library code runs unchanged inside a handler. |
| Orchestration | AWS Step Functions | Event-driven job state machine at the hosting boundary only; keeps library code sync (F1) while modelling long-running transcription jobs. |
| State / metadata | Amazon DynamoDB | Per-user job records and budget reservations; conditional writes enforce the Gate 3 per-user spend cap atomically. |
| Object storage | Amazon S3 | Stores uploaded media, `result.raw.json`, and `transcript.md`; a final `manifest.json` PUT is the atomic commit marker. |
| Auth | Amazon Cognito (+ Google IdP) | Hosted user pool with Google federation; admin-create flow gates invited users and carries the per-user budget claim. |
| API | API Gateway HTTP API | Lightweight, low-cost HTTP front for the upload/list/get Lambdas; cheaper and simpler than REST API for this surface. |
| CDN / hosting | Amazon CloudFront | Serves the static browser UI and fronts the API origin; TLS and edge caching without running a server. |
| Email | Amazon SES | Transactional email (invites, job-complete notifications) without a third-party mail provider. |
| Events | Amazon EventBridge | Decouples job lifecycle events (completion, failure, alarms) from the Step Functions flow at the hosting boundary. |
| Config / secrets | SSM Parameter Store / Secrets Manager | Provider API keys and stack config stay out of code and logs; respects the no-secrets-in-logs guardrail. |

## Quality gates (current — in `pyproject.toml` and CI)

| Layer | Choice | Rationale |
|---|---|---|
| Lint | `ruff` (selects E, F, I, UP, B; line length 100) | See [`pyproject.toml`](../pyproject.toml). |
| Type check | `mypy` (`python_version = "3.12"`, `mypy_path = "src"`) | Enforces F1–F8 contract shapes once they land. |
| Test runner | `pytest` (`asyncio_mode = "auto"`) | CI runs `ruff` + `mypy` + `pytest` on every PR. |
| Real-API tests | Manual runbooks in `tests/manual/` | Real cloud calls stay out of CI to avoid bill leaks. |

## Guardrails

See [`CLAUDE.md`](../CLAUDE.md) §"Guardrails to keep inline". Violations are
review blockers.
