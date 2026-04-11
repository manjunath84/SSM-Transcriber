# Transcriber — Implementation Plan

> **Status:** Living reference document.
> **Audience:** Any AI coding tool (Claude Code, Codex, Gemini CLI, Cursor,
> Copilot) or human contributor working on this repo.
> **How to use:** Read the phase you're currently working on. Phases build
> on each other — don't skip ahead. Each phase ends with a green PR merge
> to `main` before the next one begins.
>
> When a phase is complete, update the checkbox in `README.md` and reflect
> the new "current phase" in the AI context files (`CLAUDE.md`, `AGENTS.md`,
> `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md`).
>
> **Not the source of truth for code conventions** — those live in the AI
> context files at the repo root. This document is the *roadmap*.

---

## Context
Build a Python transcription tool that works for local video/audio files and YouTube URLs from day one, then grows incrementally into a multi-agent, provider-agnostic pipeline. The guiding principle: **ship something that transcribes before adding architecture**. Each phase leaves the project in a working, runnable state.

The full architecture (LangGraph multi-agent, cloud providers, Google Drive, Notes Agent) was designed upfront but will be introduced only when the simpler version is proven working.

**Cost philosophy:** Default to zero-cost local processing. Every cloud call is opt-in. Every paid feature is gated behind a flag or env var. The goal is that casual use costs $0.

---

## Cost Optimization Strategy

### Cost drivers and how we eliminate/reduce each

| Cost Driver | Default (free) | Opt-in paid |
|-------------|---------------|-------------|
| Transcription | `faster-whisper` local (CPU/GPU) — **$0** | Deepgram ($0.006/min), AssemblyAI ($0.009/min) |
| LLM post-processing | Skipped unless `--summarize` flag | Groq free tier → Gemini Flash → Claude Haiku (cheapest first) |
| Re-processing same file | Content-hash cache — skip if already transcribed | — |
| Cloud audio upload size | Strip silence with VAD before upload (saves 20-40% duration) | — |
| Large model on weak hardware | Default `base` model; `--quality best` opts into `large-v3` | — |

### Key cost-saving techniques applied throughout

1. **Local-first, always**: `faster-whisper` is the default and requires no API keys. Cloud providers are only used when `TRANSCRIPTION_PROVIDER` is explicitly set.

2. **`--quality` flag controls model size** (Phase 1):
   - `--quality fast` → `tiny` model (fastest, cheapest compute, ~75% accuracy)
   - `--quality balanced` → `base` model (default, good speed/accuracy)
   - `--quality best` → `large-v3` (most accurate, slower on CPU)

3. **VAD silence stripping before cloud** (Phase 1, audio extractor):
   - Use `faster-whisper`'s built-in VAD filter to detect speech-only segments
   - When routing to a cloud provider, only send speech segments — skip silence
   - Typical savings: 20-40% reduction in billable audio minutes

4. **Transcript cache** (Phase 1):
   - Cache key = SHA256 of audio file content + model/provider settings
   - Store in `~/.cache/transcriber/` (JSON files)
   - On cache hit: return cached result instantly, zero cost
   - CLI flag `--no-cache` to bypass

5. **LLM cheapest-first routing** (Phase 6):
   - LiteLLM fallback chain: `groq/llama-3.1-8b-instant` (free tier) → `gemini/gemini-1.5-flash` → `claude-haiku-4-5` → configured model
   - Prompt caching enabled for Anthropic calls (50-90% token cost reduction on repeated prompts)
   - LLM only invoked when `--summarize` or `--clean` flag is passed

6. **Audio quality pre-check** (Phase 2+):
   - Before routing to expensive cloud provider, run local SNR (signal-to-noise) check
   - If audio is clean → local faster-whisper is likely sufficient, prompt user
   - If audio is noisy + cloud requested → warn about cost before proceeding

7. **`--budget` flag** (Phase 5):
   - `--budget free` → local only, error if cloud required
   - `--budget low` → local first, cheapest cloud if local quality < threshold
   - `--budget best` → use best available provider regardless of cost

---

## GitHub Setup (do this first, before Phase 0)

**Goal:** Remote repo exists on GitHub, `main` branch is established with an initial commit.

Steps:
1. Create the repo on GitHub and wire the remote:
   ```bash
   gh repo create manjunath84/Transcriber \
     --description "Multi-agent audio/video transcription pipeline" \
     --public \
     --source /Users/manjunathans/projects/Transcriber \
     --remote origin
   ```
2. Create a minimal `README.md` with project name + one-liner description.
3. Make the initial commit and push to establish `main`:
   ```bash
   git add README.md
   git commit -m "Initial commit: Transcriber project"
   git push -u origin main
   ```
4. Verify: `gh repo view manjunath84/Transcriber` shows the repo on GitHub.

**GitHub branch strategy (per phase):**
- `main` — always contains the last fully verified, working state
- `phase/N-description` — one branch per phase; merged to `main` via PR when phase is verified
- This gives full version history and makes it easy to review what each phase added

---

## Simplified Phase Roadmap

### Phase 0 — Project Skeleton (start here)

**Goal:** `uv run transcriber --help` works; project is ready for vibe coding with any AI tool.

Files to create:
- `pyproject.toml` — minimal deps, `transcriber` CLI entry point
- `.env.example` — env vars template
- `.gitignore` — Python + uv standard ignores
- `CLAUDE.md` — Claude Code context (arch decisions, run commands, conventions)
- `AGENTS.md` — OpenAI Codex context
- `GEMINI.md` — Gemini CLI context
- `.cursorrules` — Cursor IDE rules
- `.github/copilot-instructions.md` — GitHub Copilot context
- `src/transcriber/__init__.py`
- `src/transcriber/cli.py` — typer app skeleton (commands stubbed)

**Minimal pyproject.toml deps:**
```toml
dependencies = [
  "faster-whisper>=1.0.0",
  "yt-dlp>=2024.1.0",
  "typer>=0.12.0",
  "rich>=13.7.0",
  "pydantic-settings>=2.3.0",
  "ffmpeg-python>=0.2.0",
]
```

**Git actions at end of Phase 0:**
```bash
git checkout -b phase/0-skeleton
git add .
git commit -m "Phase 0: project skeleton, CLI stub, AI tool context files"
git push -u origin phase/0-skeleton
gh pr create --title "Phase 0: project skeleton" --body "Adds pyproject.toml, CLI stub, all AI coding context files (CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, copilot-instructions.md), .gitignore, .env.example"
# merge PR → main on GitHub, then locally: git checkout main && git pull
```

**Verification:** `uv run transcriber --help` prints CLI help.

---

### Phase 0.5 — PR #1 Review Fixes (apply on `phase/0-skeleton` before merge)

**Goal:** Fix the issues found in the PR review so `main` starts from a clean, reproducible, CI-protected state.

**Fixes to apply:**

1. **Commit `uv.lock` (CRITICAL):**
   - Remove `uv.lock` line from `.gitignore`
   - Run `uv lock` if needed, `git add uv.lock`
   - Rationale: applications pin dependencies for reproducibility; libraries don't

2. **Pin Python version (HIGH):**
   - `pyproject.toml`: `requires-python = ">=3.11,<3.13"`
   - New file `.python-version` with content `3.12`
   - Run `uv sync` to re-create venv on Python 3.12 (avoids 3.14 ML-wheel incompatibility)

3. **Normalize env var prefix (MEDIUM):**
   - All **internal** settings get `TRANSCRIBER_` prefix: `TRANSCRIBER_WHISPER_MODEL_SIZE`, `TRANSCRIBER_WHISPER_DEVICE`, `TRANSCRIBER_TRANSCRIPTION_PROVIDER`, `TRANSCRIBER_DEFAULT_BUDGET`, `TRANSCRIBER_OUTPUT_DIR`, `TRANSCRIBER_CACHE_DIR`, `TRANSCRIBER_CACHE_ENABLED`, `TRANSCRIBER_LOG_LEVEL`
   - **Third-party** API keys stay unprefixed (SDKs read them directly): `DEEPGRAM_API_KEY`, `ASSEMBLYAI_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`
   - Update `.env.example` accordingly

4. **Add typing + config stub (LOW):**
   - Create empty `src/transcriber/py.typed`
   - Create `src/transcriber/config.py` with a minimal `TranscriberSettings(BaseSettings)` stub that reads `TRANSCRIBER_*` vars with `env_prefix="TRANSCRIBER_"`; this unblocks the references in the AI context files and is ready for Phase 1 to extend

5. **Add GitHub Actions CI (NEW):**
   - Create `.github/workflows/ci.yml` running on PRs to `main` and pushes to `main`:
     - Setup uv (`astral-sh/setup-uv@v3`)
     - `uv sync --all-extras --dev`
     - `uv run ruff check src/`
     - `uv run mypy src/`
     - `uv run pytest`
   - This protects `main` from regressions as you vibe code with multiple AI tools

6. **Project name decision (DEFERRED — user call):**
   - Current: `Transcriber` (missing 'r', should be `Transcriber`)
   - This is a branding decision, not a technical one
   - If renamed later: affects GitHub repo, package name, CLI entry point, import paths, 6 context files — cheap now, expensive after Phase 1
   - **Not blocking this PR** — flag for user confirmation before merge

**Git actions for Phase 0.5:**
```bash
# on branch phase/0-skeleton
git add uv.lock .python-version pyproject.toml .gitignore .env.example \
        src/transcriber/py.typed src/transcriber/config.py .github/workflows/ci.yml
git commit -m "Phase 0 review fixes: pin Python, commit lockfile, CI, env prefix"
git push
# PR #1 auto-updates; CI runs on push
```

**Verification:**
- `uv sync` completes on Python 3.12 (not 3.14)
- `git ls-files | grep uv.lock` shows the lockfile is tracked
- CI workflow runs green on the pushed commit
- `grep TRANSCRIBER_ .env.example` shows all internal vars prefixed

---

### Phase 1 — MVP: Transcribe a Local File (working end-to-end)

**Goal:** `uv run transcriber transcribe ./video.mp4` produces `./video.txt` with the transcript.

Files to create/modify:
- `src/transcriber/core/audio_extractor.py` — ffmpeg-python: extract audio from video → 16kHz mono WAV; strip silence using faster-whisper VAD before returning
- `src/transcriber/core/transcriber.py` — faster-whisper wrapper: load model lazily (singleton), transcribe WAV, return segments + full text
- `src/transcriber/core/cache.py` — SHA256-based transcript cache: `get(cache_key)` / `set(cache_key, result)`; stores JSON in `~/.cache/transcriber/`
- `src/transcriber/config.py` — pydantic-settings: reads `.env` for `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE`, `OUTPUT_DIR`, `CACHE_DIR`, `CACHE_ENABLED`
- `src/transcriber/cli.py` — wire `transcribe` command with `--quality` and `--no-cache` flags

**Simple flow (no agents, no abstraction yet):**
```
CLI input (file path)
  → compute cache_key (SHA256 of file + quality setting)
  → cache.get(cache_key) → return immediately if hit (cost: $0)
  → audio_extractor.extract(path) → 16kHz mono WAV (silence stripped)
  → transcriber.transcribe(wav_path, quality) → TranscriptResult
  → cache.set(cache_key, result)
  → write to output file (txt)
  → print summary (duration transcribed, model used, cache hit/miss)
```

**Key implementation details:**
- `TranscriptResult` is a simple dataclass: `full_text`, `segments` (list of `{start, end, text}`), `language`, `duration`, `speech_duration` (after VAD — what you'd pay for on cloud)
- Quality-to-model mapping: `fast→tiny`, `balanced→base` (default), `best→large-v3`
- VAD filter always on for audio extraction — reduces duration billed if ever routed to cloud
- Model loaded once and reused across calls (avoid reload penalty)
- Rich progress spinner + show "Cache hit — skipped transcription" when applicable

**CLI interface:**
```bash
uv run transcriber transcribe ./interview.mp4
uv run transcriber transcribe ./podcast.mp3 --output ./notes.txt --quality best
uv run transcriber transcribe ./lecture.mp4 --quality fast --language en
uv run transcriber transcribe ./lecture.mp4 --no-cache   # force re-transcription
```

**Test fixture (required for Phase 1 verification):**
- Create `tests/fixtures/short_speech.wav` — a ≤10 second clip with real speech (not synthetic tones)
- Source: record yourself saying "Hello, this is a transcription test" with `sox` or `ffmpeg -f avfoundation`, or download a CC0 sample
- Commit the fixture (small enough: ~160KB at 16kHz mono)

**Unit tests for Phase 1:**
- `tests/unit/test_cache.py` — cache hit/miss, SHA256 key stability across runs
- `tests/unit/test_audio_extractor.py` — video → WAV conversion, silence stripping
- `tests/unit/test_transcriber.py` — uses `short_speech.wav` fixture, asserts non-empty result
- Phase 1 is not "done" until verification + unit tests pass locally AND in CI

**Git actions at end of Phase 1:**
```bash
git checkout main && git pull
git checkout -b phase/1-local-transcription
# ... implement, run tests, verify ...
# Update README.md roadmap: check off Phase 1
git add .
git commit -m "Phase 1: MVP local file transcription with faster-whisper"
git push -u origin phase/1-local-transcription
gh pr create --title "Phase 1: local file transcription MVP"
```

**Verification:** Transcribe `tests/fixtures/short_speech.wav` and assert the output text contains expected words; all unit tests pass; CI green.

---

### Phase 2 — Add YouTube Support

**Goal:** `uv run transcriber transcribe "https://youtu.be/..."` works.

Files to create/modify:
- `src/transcriber/sources/youtube.py` — yt-dlp wrapper: download audio-only to temp dir, return local WAV path + metadata (title, duration)
- `src/transcriber/sources/local.py` — thin wrapper around local file (mirrors YouTube interface)
- `src/transcriber/sources/__init__.py` — `resolve_source(uri)`: returns correct source based on URI pattern (URL → YouTube, path → local)
- `src/transcriber/cli.py` — update `transcribe` to call `resolve_source()` first, then existing pipeline

**Source detection logic:**
```python
def resolve_source(uri: str) -> Source:
    if uri.startswith(("http://", "https://", "youtu.be")):
        return YouTubeSource()
    return LocalSource()
```

**Verification:** `uv run transcriber transcribe "https://youtu.be/dQw4w9WgXcQ"` produces a transcript.

---

### Phase 3 — Output Formats + Polish

**Goal:** Support SRT, JSON, and Markdown output; quality-of-life improvements.

Files to create/modify:
- `src/transcriber/formatters/text.py` — plain text (current default)
- `src/transcriber/formatters/srt.py` — SRT subtitle format from segments
- `src/transcriber/formatters/markdown.py` — paragraphs with optional timestamps
- `src/transcriber/formatters/json_fmt.py` — full JSON with segments
- `src/transcriber/formatters/__init__.py` — `get_formatter(format_str)` factory
- `src/transcriber/cli.py` — add `--format txt|srt|md|json` flag

**CLI additions:**
```bash
uv run transcriber transcribe ./video.mp4 --format srt
uv run transcriber transcribe "https://youtu.be/..." --format md --output notes.md
```

**Verification:** All 4 output formats produce valid files.

---

### Phase 4 — Google Drive Source

**Goal:** `uv run transcriber transcribe "drive://FILE_ID"` works after auth.

Files to create/modify:
- `src/transcriber/sources/google_drive.py` — OAuth2 flow + `google-api-python-client` download
- `src/transcriber/cli.py` — add `transcriber auth google-drive` command for OAuth setup
- `src/transcriber/sources/__init__.py` — add `drive://` pattern to `resolve_source()`
- Add to `pyproject.toml`: `google-api-python-client`, `google-auth-oauthlib`

**Auth flow:**
```bash
uv run transcriber auth google-drive   # opens browser, saves token
uv run transcriber transcribe "drive://1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
```

**Verification:** Transcribe a video file stored in Google Drive.

---

### Phase 5 — Cloud Transcription Providers (provider abstraction)

**Goal:** Swap transcription engine via env var; `--budget` flag enforces cost ceiling.

Files to create/modify:
- `src/transcriber/providers/base.py` — `TranscriptionProvider` ABC; add `cost_per_minute: float` property (0.0 for local)
- `src/transcriber/providers/faster_whisper.py` — wrap existing core/transcriber.py; `cost_per_minute = 0.0`
- `src/transcriber/providers/deepgram.py` — Deepgram Nova-2; `cost_per_minute = 0.006` (cheapest accurate cloud option)
- `src/transcriber/providers/assemblyai.py` — AssemblyAI; `cost_per_minute = 0.009`
- `src/transcriber/providers/openai_whisper.py` — OpenAI Whisper API; `cost_per_minute = 0.02`
- `src/transcriber/providers/__init__.py` — registry + `get_provider(name)` factory + `get_cheapest_provider()` helper
- `src/transcriber/core/budget_router.py` — routes to correct provider based on `--budget`:
  - `free` → always `faster_whisper`, error if unavailable
  - `low` → `faster_whisper` first; if `--quality best` and audio > 10 min, suggest Deepgram
  - `best` → use configured `TRANSCRIPTION_PROVIDER` or best available
- `src/transcriber/config.py` — add `TRANSCRIPTION_PROVIDER`, `DEFAULT_BUDGET` settings
- CLI: add `--budget free|low|best` flag (default: `free`)
- Before any cloud call: print estimated cost (`speech_duration_min × cost_per_minute`) and confirm unless `--yes` flag

**Cost display example (before cloud call):**
```
  Audio duration : 45.2 min (speech only, after VAD)
  Provider       : Deepgram Nova-2
  Estimated cost : ~$0.27
  Proceed? [y/N]
```

Add to `pyproject.toml`: `deepgram-sdk`, `assemblyai`, `openai`, `tenacity`

**Retry strategy (required for all cloud calls):**
- Wrap provider network calls with `tenacity.retry`:
  - Retry on: HTTP 429, 503, network timeouts
  - 3 attempts max, exponential backoff (1s → 2s → 4s)
  - Never retry on 4xx (other than 429) — those are user errors
- Failed retries surface a clear CLI error with the last exception message

**Verification:** `--budget free uv run transcriber transcribe ./audio.mp3` uses local only; cloud providers prompt for cost confirmation; simulated 429 triggers retry then success.

---

### Phase 6a — LLM Post-Processing (opt-in, cheapest-first)

**Goal:** `--summarize` and `--clean` flags work with zero default cost. No framework migration yet.

Files to create/modify:
- Add `litellm` to `pyproject.toml`
- `src/transcriber/llm/__init__.py`
- `src/transcriber/llm/provider.py` — LiteLLM wrapper with **cheapest-first fallback chain**:
  1. `groq/llama-3.1-8b-instant` (free tier, ~100K tokens/day)
  2. `gemini/gemini-1.5-flash` (~$0.075/1M tokens)
  3. `claude-haiku-4-5` (~$0.25/1M tokens, prompt caching enabled)
  4. Configured `TRANSCRIBER_LLM_MODEL` override
- `src/transcriber/llm/chunker.py` — splits long transcripts into chunks before LLM calls (avoids large context window costs); summarizes each chunk then combines
- `src/transcriber/llm/prompts.py` — system prompts for `summarize` and `clean` tasks
- `src/transcriber/cli.py` — wire `--summarize` and `--clean` flags (both off by default = $0 LLM cost)

**LLM cost controls:**
- `--summarize` / `--clean` are opt-in only — default run has zero LLM cost
- Chunked summarization: never send more tokens than needed; 4K chunk default
- Prompt caching on Anthropic: system prompt cached, only transcript diff billed
- Print estimated LLM token count before processing if > 10K tokens

**Verification:** `transcriber transcribe ./video.mp4 --summarize` produces transcript + summary using free Groq tier by default.

---

### Phase 6b — LangGraph Multi-Agent Foundation

**Goal:** Migrate pipeline to LangGraph state machine; expose Transcriber agent contract for future Notes Agent.

Files to create/modify:
- Add `langgraph`, `langchain-core` to `pyproject.toml`
- `src/transcriber/agents/__init__.py`
- `src/transcriber/agents/state.py` — `TranscriberState` Pydantic model (input URI, stage, media metadata, audio path, transcription result, final output, messages)
- `src/transcriber/agents/graph.py` — LangGraph graph wrapping existing pipeline stages as nodes (fetch → extract → transcribe → post-process → format)
- `src/transcriber/agents/nodes.py` — one async function per pipeline stage; each returns `dict` of state updates
- `src/transcriber/cli.py` — `transcribe` command calls `graph.ainvoke(initial_state)` instead of the direct pipeline

**Notes Agent interface (forward-compatible):**
The graph emits a `transcription_complete` event as a LangGraph message at the end. Future Notes Agent (separate repo) subscribes to this — consumes the transcript without re-transcribing (zero re-processing cost).

**Contract file** (consumed by future Notes Agent):
- `src/transcriber/contracts.py` — `TranscriptionResult` Pydantic model as the shared contract
- Future: extract to a tiny `transcriber-contracts` package both agents depend on

**Verification:** `transcriber transcribe ./video.mp4` still works end-to-end, now via LangGraph; graph visualization (`graph.get_graph().draw_ascii()`) shows all 5 nodes.

---

## Critical Files (in order of creation)

| Phase | File | Purpose |
|-------|------|---------|
| GH | GitHub repo `manjunath84/Transcriber` | Remote origin, PR-based phase tracking |
| 0 | `pyproject.toml` | All dependencies, CLI entry point |
| 0 | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md` | AI tool context |
| 0 | `src/transcriber/cli.py` | Typer CLI skeleton |
| 1 | `src/transcriber/core/audio_extractor.py` | ffmpeg audio extraction |
| 1 | `src/transcriber/core/transcriber.py` | faster-whisper wrapper |
| 1 | `src/transcriber/config.py` | pydantic-settings config |
| 2 | `src/transcriber/sources/youtube.py` | yt-dlp YouTube download |
| 2 | `src/transcriber/sources/__init__.py` | Source resolver |
| 3 | `src/transcriber/formatters/` | Output format modules |
| 4 | `src/transcriber/sources/google_drive.py` | Google Drive source |
| 5 | `src/transcriber/providers/` | Provider abstraction + cloud engines |
| 6 | `src/transcriber/agents/` | LangGraph multi-agent foundation |

---

## AI Coding Context File Strategy

All 5 files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md`) contain the same core information adapted for each tool's format:
- Project purpose and run commands (`uv sync`, `uv run transcriber --help`)
- Current phase and what's implemented vs stubbed
- Architecture conventions (async, no hardcoded provider names, etc.)
- Where to add new sources / providers / formatters

These files get updated at the end of each phase to reflect what's now implemented.

---

## Verification (End-to-End Test per Phase)

- **GitHub setup:** `gh repo view manjunath84/Transcriber` shows the repo; `git remote -v` shows `origin`
- **Phase 0:** `uv run transcriber --help` shows commands
- **Phase 0.5:** CI green on PR #1; `uv.lock` tracked; Python 3.12 venv; all internal env vars prefixed `TRANSCRIBER_`; PR merged to `main`
- **Phase 1:** `uv run transcriber transcribe tests/fixtures/short_speech.wav` → correct transcript; unit tests pass; CI green
- **Phase 2:** `uv run transcriber transcribe "https://youtu.be/..."` → transcript file
- **Phase 3:** `uv run transcriber transcribe short.wav --format srt` → valid SRT file
- **Phase 4:** `uv run transcriber auth google-drive && uv run transcriber transcribe "drive://ID"` → transcript
- **Phase 5:** `TRANSCRIBER_TRANSCRIPTION_PROVIDER=deepgram uv run transcriber transcribe short.wav` → Deepgram transcript with cost prompt
- **Phase 6a:** `uv run transcriber transcribe short.wav --summarize` → transcript + summary via Groq free tier
- **Phase 6b:** Same as 6a but now running through LangGraph; graph visualization shows all nodes

## Cross-phase practices (apply at the end of every phase)

1. **README roadmap checkbox** — tick off the completed phase in `README.md` before opening the PR
2. **CI must be green** — no phase merges until ruff, mypy, and pytest all pass on the PR
3. **AI context files updated** — each phase updates `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md` to reflect the new "current phase" and any new conventions
4. **Phase branch deleted after merge** — keep the branch list clean
