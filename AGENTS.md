# SSM-Transcriber — Agent Instructions

> **Roadmap:** See [`docs/PLAN.md`](docs/PLAN.md) for the phased
> implementation plan and cost strategy.

## Project
Multi-agent audio/video transcription pipeline. Python 3.12, managed with `uv`.

## Stack
- Transcription: `faster-whisper` (local, free) + Deepgram / AssemblyAI / OpenAI (cloud, opt-in)
- LLM: `litellm` (cloud-agnostic — Groq → Gemini → Claude by cost)
- Agents: `langgraph` (Phase 6+)
- CLI: `typer` + `rich`
- Config: `pydantic-settings`

## Commands
```bash
uv sync                          # install deps
uv run ssm-transcriber --help
uv run ssm-transcriber transcribe ./video.mp4
uv run pytest
uv run ruff check src/
```

## Current phase: 0 — Skeleton
Only the CLI stub and config files exist. Transcription not yet implemented.

## Pipeline (when fully built)
```
URI input
  → RunWorkspace (temp dir, try/finally cleanup)   [F5]
  → resolve_source(uri) → source.prepare()
      → PreparedMedia(kind, local_path, workspace, ...)  [F2]
  → CacheKey composite → cache.get() on hit returns          [F3]
  → audio_extractor.extract() → canonical WAV (full timeline)
  → audio_extractor.vad_sidecar() → speech regions (cost only)
  → transcriber.transcribe(wav) → TranscriptResult
  → cache.set() [atomic]
  → formatter.format(result) → atomic write to output
```

## File layout
```
src/transcriber/
  cli.py               # typer entry point
  config.py            # pydantic-settings singleton
  core/                # audio_extractor, transcriber, cache   [Phase 1]
  sources/             # local, youtube, google_drive          [Phase 2-4]
  formatters/          # txt, srt, md, json                    [Phase 3]
  providers/           # provider ABC + cloud engines          [Phase 5]
  agents/              # LangGraph state + graph               [Phase 6]
```

## Rules
- Never read `os.environ` directly — use `from transcriber.config import settings`
- **Sync through Phase 4** — no `async def` on pipeline, source, provider, or formatter methods. Every library in the stack is blocking-native. Revisit at Phase 5. (Phase 1 Foundations F1)
- Cache keys are **versioned composites**: audio hash + provider id + model id + model revision + language + VAD mode + schema version. Never cache on just file hash + quality. (F3)
- Two-gate spend model: "key configured" ≠ "provider allowed". `--budget free` rejects paid providers regardless of keys. Paid LLM fallback requires `--allow-paid-llm` + confirmation. (F4)
- Every run uses a single `RunWorkspace` (temp dir) with `try/finally` cleanup; output writes are atomic via `os.replace()`. (F5)
- Sources return `PreparedMedia` (F2) — the pipeline never sees raw URIs
- VAD is a sidecar artifact, not a transform of the canonical audio — timestamps must match the original timeline
- Never log secrets; use `settings.redacted_dump()` for diagnostic output
- Before any cloud API call: compute and display estimated cost from `speech_duration`, require confirmation
- Default budget is `free` — local only, zero spend

## Where these rules come from
All of the above are formalized in `docs/PLAN.md` → "Phase 1 Foundations" (F1–F8). If this file conflicts with `docs/PLAN.md`, `docs/PLAN.md` wins and this file should be updated.

## Author context — teaching register and interview prep
Primary author is a senior Java developer transitioning to AI/ML engineering. Learning artifacts live in [`docs/learn/`](docs/learn/README.md). On every PR, apply these rules:
- **Teaching register by default.** Explain the *why*; give a Java analogue when a Python/AI concept first appears.
- **Update living docs in the same PR.** Idioms → [`python-notes.md`](docs/learn/python-notes.md). AI/ML terms → [`glossary.md`](docs/learn/glossary.md). PR explainer → `docs/learn/prs/pr-NNN-<slug>.md`.
- **Cite real files.** Broken pointers in learning docs block review. Full conventions: [`docs/learn/README.md`](docs/learn/README.md). Teaching register does not override `docs/PLAN.md` F1–F8.
