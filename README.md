# SSM-Transcriber

Multi-agent audio/video transcription pipeline — local-first, cloud-agnostic, cost-optimized.

Transcribe video and audio from **local files**, **YouTube URLs**, and **Google Drive** using a provider-swappable pipeline. Default transcription runs entirely locally with no API keys required.

## Quick start

```bash
uv sync
uv run ssm-transcriber transcribe ./video.mp4
uv run ssm-transcriber transcribe "https://youtu.be/..."
```

## Cost model

| Mode | Cost |
|------|------|
| Local transcription (default) | **$0** — runs on your machine |
| Cloud transcription (opt-in) | From $0.006/min — prompted before any spend |
| LLM summarization (opt-in) | Free tier first (Groq), paid only as fallback |

## Roadmap

- [x] GitHub repo + project setup
- [ ] Phase 0: Project skeleton + CLI stub
- [ ] Phase 1: Local file transcription (faster-whisper)
- [ ] Phase 2: YouTube source (yt-dlp)
- [ ] Phase 3: Output formats (txt, srt, md, json)
- [ ] Phase 4: Google Drive source
- [ ] Phase 5: Cloud transcription providers (Deepgram, AssemblyAI)
- [ ] Phase 6: LLM summarization + multi-agent foundation (LangGraph)

## Stack

- **Transcription**: `faster-whisper` (local) · Deepgram · AssemblyAI · OpenAI Whisper
- **LLM**: `litellm` — cloud-agnostic (Groq → Gemini → Claude Haiku by cost)
- **Agents**: `langgraph` (Phase 6+)
- **Package manager**: `uv`
- **CLI**: `typer` + `rich`
