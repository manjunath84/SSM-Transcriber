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

## Transcription quick-start

```bash
# Install
git clone https://github.com/manjunath84/SSM-Transcriber
cd SSM-Transcriber
uv sync

# Transcribe a local file (free — uses faster-whisper locally)
# Note: Phase 1 (local faster-whisper) is not yet built.
# The working path today is cloud transcription via AssemblyAI (see below).

# Transcribe via AssemblyAI (requires ASSEMBLYAI_API_KEY in .env)
uv run ssm-transcriber transcribe ./recording.mp4 --budget low

# Transcribe a Google Drive file (public link)
uv run ssm-transcriber transcribe "drive://FILE_ID" --budget low

# See all options
uv run ssm-transcriber transcribe --help
```

## Google Drive upload

Transcripts can be uploaded to Google Drive after transcription, or
uploaded separately from an existing file.

### One-time setup

1. Go to [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services** → **Library**. Search for **Google Drive API** and enable it.
2. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**. Choose **Desktop app**, download the JSON, and copy the client ID and secret.
3. Add to your `.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=your-client-id
   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
   TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID=your-folder-id
   ```
   Find a folder ID by opening the folder in Drive — it's the last segment of the URL.
4. Run the one-time auth flow:
   ```bash
   uv run ssm-transcriber auth google-drive
   ```
   A browser window opens for consent. The token is saved to `~/.config/transcriber/google_token.json`.

### Usage

```bash
# Transcribe and upload in one step
uv run ssm-transcriber transcribe "drive://FILE_ID" --budget low --upload-to-drive

# Upload a previously-transcribed file
uv run ssm-transcriber upload ./output/Session20-transcript-2026-05-05.md

# Override the default folder for one run
uv run ssm-transcriber upload ./output/session.md --drive-folder OTHER_FOLDER_ID
```

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
- [ ] Phase 5: Cloud transcription providers (Deepgram, AssemblyAI, OpenAI Whisper) + two-gate spend model; Hugging Face remains a later experimental hosted option
- [ ] Phase 6: LLM summarization + multi-agent foundation (LangGraph)

All phases build on the **Phase 1 Foundations** (`PreparedMedia`, versioned cache keys,
two-gate spend model, `RunWorkspace`, sync-by-default, fixture/stub strategy) defined in
[`docs/PLAN.md`](docs/PLAN.md). CI runs `ruff` + `mypy` + `pytest` on every PR.

See [`specs/`](specs/) for the SDD constitution (mission, tech-stack, roadmap) and per-feature specs.

## Stack

- **Transcription**: `faster-whisper` (local) · Deepgram · AssemblyAI · OpenAI Whisper
- **Experimental later**: Hugging Face Inference Providers as an explicit-only hosted provider candidate
- **LLM**: `litellm` — cloud-agnostic (Groq → Gemini → Claude Haiku by cost)
- **Agents**: `langgraph` (Phase 6+)
- **Package manager**: `uv`
- **CLI**: `typer` + `rich`
