# SSM-Transcriber

Multi-agent audio/video transcription pipeline — local-first, cloud-agnostic, cost-optimized.

Transcribe video and audio from **local files**, **YouTube URLs**, and **Google Drive** using a provider-swappable pipeline. Default transcription runs entirely locally with no API keys required.

## Quick start

```bash
uv sync
uv run ssm-transcriber transcribe ./video.mp4
uv run ssm-transcriber transcribe "https://youtu.be/..."
```

> **First-run note:** `faster-whisper` downloads model weights on first use
> (`tiny` ≈ 75 MB, `base` ≈ 145 MB, `large-v3` ≈ 3 GB). Prefetch with
> `uv run ssm-transcriber models download --quality balanced` to avoid waiting
> on the first transcribe call or surprising an offline run.

## Cost model

| Mode | Cost |
|------|------|
| Local transcription (default) | **$0** — runs on your machine |
| Cloud transcription (opt-in) | From $0.006/min — prompted before any spend |
| LLM summarization (opt-in) | Free tier first (Groq), paid only as fallback |

## Roadmap

- [x] GitHub repo + project setup
- [x] Phase 0: Project skeleton + CLI stub (CI with ruff / mypy / pytest, lockfile committed, Python 3.12 pinned)
- [ ] Phase 1: Local file transcription (faster-whisper) — foundations (F1–F8) are defined in [`docs/PLAN.md`](docs/PLAN.md)
- [ ] Phase 2: YouTube source (yt-dlp)
- [ ] Phase 3: Output formats (txt, srt, md, json)
- [ ] Phase 4: Google Drive source
- [ ] Phase 5: Cloud transcription providers (Deepgram, AssemblyAI) + two-gate spend model
- [ ] Phase 6: LLM summarization + multi-agent foundation (LangGraph)

All phases build on the **Phase 1 Foundations** (`PreparedMedia`, versioned cache keys,
two-gate spend model, `RunWorkspace`, sync-by-default, fixture/stub strategy) defined in
[`docs/PLAN.md`](docs/PLAN.md). CI runs `ruff` + `mypy` + `pytest` on every PR.

## Stack

- **Transcription**: `faster-whisper` (local) · Deepgram · AssemblyAI · OpenAI Whisper
- **LLM**: `litellm` — cloud-agnostic (Groq → Gemini → Claude Haiku by cost)
- **Agents**: `langgraph` (Phase 6+)
- **Package manager**: `uv`
- **CLI**: `typer` + `rich`
