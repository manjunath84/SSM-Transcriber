# SSM-Transcriber — Implementation Plan

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

1. **Local-first, always**: `faster-whisper` is the default and requires no API keys. Paid providers are only considered when both the budget allows them (`--budget low|best`) and their key is configured — any paid call still requires cost confirmation unless `--yes` is passed (see [F4](#f4-spend-permission--separate-configured-from-allowed)).

2. **`--quality` flag controls model size** (Phase 1):
   - `--quality fast` → `tiny` model (fastest, cheapest compute, ~75% accuracy)
   - `--quality balanced` → `base` model (default, good speed/accuracy)
   - `--quality best` → `large-v3` (most accurate, slower on CPU)

3. **VAD as a sidecar artifact, not a transform of the canonical audio** (Phase 1):
   - Use `faster-whisper`'s VAD filter to compute speech-only regions as a sidecar table (`[(start, end)]` on the **original** timeline)
   - The canonical transcription path always runs on the full, unmodified audio so segment timestamps remain truthful for SRT/markdown output (Phase 3)
   - The sidecar is used only for: (a) cost estimation (`speech_duration`), (b) building a reduced upload when a cloud provider is invoked (Phase 5)
   - See [Phase 1 Foundations](#phase-1-foundations-contracts-that-later-phases-depend-on) for the full contract

4. **Transcript cache** (Phase 1, versioned key):
   - Cache key is a **versioned composite** — see [Phase 1 Foundations](#phase-1-foundations-contracts-that-later-phases-depend-on) for the canonical schema
   - At minimum: canonical audio content hash + provider id + model id/revision + language override + VAD mode + pipeline schema version
   - Store in `~/.cache/transcriber/` (JSON files) keyed by the composite hash
   - On cache hit: return cached result without model load or transcription (extraction still runs to compute the content hash — see the [Phase 1 flow](#phase-1--mvp-transcribe-a-local-file-working-end-to-end))
   - CLI flag `--no-cache` to bypass
   - Any change to the schema bumps `pipeline_schema_version` and invalidates old entries (safe by construction)

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
   gh repo create manjunath84/SSM-Transcriber \
     --description "Multi-agent audio/video transcription pipeline (SSM-Transcriber)" \
     --public \
     --source /Users/manjunathans/projects/Transcriber \
     --remote origin
   ```
2. Create a minimal `README.md` with project name + one-liner description.
3. Make the initial commit and push to establish `main`:
   ```bash
   git add README.md
   git commit -m "Initial commit: SSM-Transcriber project"
   git push -u origin main
   ```
4. Verify: `gh repo view manjunath84/SSM-Transcriber` shows the repo on GitHub.

**GitHub branch strategy (per phase):**
- `main` — always contains the last fully verified, working state
- `phase/N-description` — one branch per phase; merged to `main` via PR when phase is verified
- This gives full version history and makes it easy to review what each phase added

---

## Simplified Phase Roadmap

### Phase 0 — Project Skeleton (start here)

**Goal:** `uv run ssm-transcriber --help` works; project is ready for vibe coding with any AI tool.

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

**Verification:** `uv run ssm-transcriber --help` prints CLI help.

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

### Phase 1 Foundations (contracts that later phases depend on)

**Why this section exists:** Several Phase 1 decisions are load-bearing for
Phases 2–6. Getting them wrong is cheap to fix now and expensive to fix after
YouTube, cloud providers, formatters, and LangGraph pile on top. This section
is the **single source of truth** for these contracts — the root tool files,
`docs/ai/README.md`, and any workflow runbooks must agree with it.

#### F1. Sync vs. async (decision: sync through Phase 4)

The Phase 0 skeleton is synchronous, and every library in the core stack
(`ffmpeg-python`, `yt-dlp`, `faster-whisper`, `google-api-python-client`) is
blocking-native. We will **keep the core pipeline synchronous through Phase 4**.
Revisit async at Phase 5 only if a real concurrency need emerges (e.g.
overlapping cloud uploads, streaming providers).

- Do not introduce `async def` on pipeline, source, provider, or formatter
  methods until there is a concrete benefit to measure
- CLI stays sync end-to-end; no `asyncio.run()` at the entry point
- LangGraph (Phase 6b) may use async internally — that is isolated behind the
  graph boundary and does not leak into sources/providers

#### F2. `PreparedMedia` — the source→pipeline contract

Phase 1 must define the contract that Phase 2 (YouTube), Phase 4 (Google Drive),
and Phase 5 (cloud providers) will all consume. Defining it now as a plain
dataclass costs nothing; retrofitting it later is a full sweep of every source
and provider.

```python
# src/transcriber/sources/base.py
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SourceKind = Literal["local", "youtube", "google_drive"]

@dataclass(frozen=True)
class PreparedMedia:
    """Everything downstream stages need to transcribe a piece of media.

    The `workspace` field owns cleanup — the caller that created the
    PreparedMedia owns the workspace and is responsible for cleanup on
    both success and failure (see F5).
    """
    kind: SourceKind
    original_uri: str              # the URI the user passed in
    local_path: Path               # resolved local file — always present
    title: str | None              # human-readable media title, if known
    duration_seconds: float | None # media duration, if known pre-transcription
    workspace: "RunWorkspace"      # temp-dir lifecycle (see F5)
    extra: dict[str, str]          # source-specific metadata (yt-dlp tags, etc.)
```

In Phase 1, only `LocalSource` exists and returns a `PreparedMedia` whose
`local_path` equals the user's input path. Phase 2 adds `YouTubeSource` and
`resolve_source()`. The pipeline never sees raw URIs — it sees `PreparedMedia`.

**Source resolution (Phase 2):** match URLs by **hostname**, not scheme. The
resolver should be a list of `(matcher, source_class)` pairs tried in order:

```python
# WRONG — what the earlier draft implied
if uri.startswith(("http://", "https://")): return YouTubeSource()

# RIGHT — Phase 2 must do this
from urllib.parse import urlparse
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
def is_youtube(uri: str) -> bool:
    try:
        return urlparse(uri).hostname in YOUTUBE_HOSTS
    except ValueError:
        return False
```

#### F3. Cache key — versioned composite schema

Replaces the old "SHA256(file + quality)" shorthand in one place so every AI
tool sees the same thing.

```python
# src/transcriber/core/cache.py
PIPELINE_SCHEMA_VERSION = 1  # bump on ANY change below

@dataclass(frozen=True)
class CacheKey:
    audio_sha256: str          # SHA256 of the CANONICAL audio file bytes
                               # (always the extracted 16kHz mono WAV, never the raw
                               #  container — normalises across formats and sources)
    provider_id: str           # "faster_whisper" | "deepgram" | ...
    model_id: str              # "base" | "large-v3" | "nova-2" | ...
    model_revision: str        # faster-whisper release or HF revision hash
    language: str              # user override or "auto"
    vad_mode: str              # "off" | "silero-v4-default" | ...
    pipeline_schema_version: int = PIPELINE_SCHEMA_VERSION

    def digest(self) -> str:
        # stable JSON dump → SHA256 → hex
        ...
```

**Rules:**
- Never cache on "file path + quality flag" alone — that masks real differences
- `model_revision` is required; `faster-whisper` model files have stable SHAs,
  record whichever the loader exposes (fall back to model package version)
- Changing the dataclass → bump `PIPELINE_SCHEMA_VERSION` → old entries invalidate
- Cache file layout: `~/.cache/transcriber/v{schema}/{digest}.json` so old
  schema versions can be garbage-collected with `rm -rf`

#### F4. Spend permission — separate "configured" from "allowed"

"Key exists" must never mean "key will be used." The permission model is a
two-step gate:

| Step | What it checks | Source |
|------|----------------|--------|
| 1. Configured | Is there a key/endpoint for this provider? | env vars, `.env` |
| 2. Allowed | Does the current budget/flag permit paid use? | `--budget`, `--summarize`, `--allow-paid-llm` |

Rules:
- `--budget free` (default) → only providers with `cost_per_minute == 0.0` are
  allowed, even if paid API keys are configured. Attempting a paid provider
  exits non-zero with a clear message.
- `--budget low` / `--budget best` → paid providers become *candidates*; the
  user still sees an estimated cost and must confirm (or pass `--yes`).
- LLM post-processing (Phase 6a): `--summarize` / `--clean` default to the free
  tier (Groq). Falling back to any paid LLM requires **both** a paid key *and*
  `--allow-paid-llm` *and* a cost confirmation. No silent fallback.
- Every confirmation prompt shows: provider, estimated minutes/tokens,
  estimated cost, and the flag that would skip the prompt (`--yes`). Cost
  estimates come from the `speech_duration` sidecar (see VAD, above), not the
  full media duration.

#### F5. Temp files and interruption — `RunWorkspace`

Every run gets a dedicated temp directory with well-defined ownership. This
prevents leaked WAVs, half-written outputs, and "it crashed and now my cache
is poisoned" bugs.

```python
# src/transcriber/core/workspace.py
class RunWorkspace:
    """Per-run temp dir. Use as a context manager at the CLI boundary."""
    root: Path                          # e.g. /tmp/transcriber-xyz123/
    def path(self, name: str) -> Path: ...
    def __enter__(self) -> "RunWorkspace": ...
    def __exit__(self, *exc) -> None:   # deletes root unless keep=True
        ...
```

Rules:
- The CLI creates exactly one `RunWorkspace` per invocation and passes it down.
  Sources and the extractor write into `workspace.path("…")`; nobody else
  creates their own `tempfile.mkdtemp`.
- The cleanup is **`try/finally` on the workspace context manager**, not on
  per-file handlers, so Ctrl-C (SIGINT) still cleans up.
- `--keep-temp` flag preserves the workspace for debugging and prints its path.
- Output writes are **atomic**: write to `{output}.tmp` in the **same directory
  as the final output** (not in the workspace), then `os.replace()` into the
  final path. This avoids cross-device rename failures when the workspace is
  on a different filesystem (e.g. `/tmp` vs. the user's home directory). A
  Ctrl-C mid-write never leaves a truncated `.txt`/`.srt`/`.json`.
- Cache writes use the same atomic pattern: temp file created inside
  `~/.cache/transcriber/`, then `os.replace()` to the final cache path.

#### F6. Model download preflight (first-run UX)

`faster-whisper` downloads model weights on first use (`tiny`≈75MB, `base`≈145MB,
`large-v3`≈3GB). This is a network dependency even though it isn't billable.
Phase 1 must:

- On first run, detect missing model files and print a one-line notice:
  `Downloading faster-whisper '{model}' (~{size}MB) to ~/.cache/huggingface/...`
- Expose an explicit `ssm-transcriber models download [--quality fast|balanced|best]`
  command (Phase 1) so users can prefetch offline
- Mention the download requirement in `README.md` under "Quick start"
- Never silently fail when offline: surface the network error with a pointer
  to `models download`

#### F7. Mocks, fixtures, and test strategy

A single smoke-test fixture is not enough past Phase 1. Define the test
surface once, here, so every phase adds to the same harness.

**Fixtures (committed to `tests/fixtures/`):**
- `short_speech.wav` — ≤10s, real speech, for smoke-level transcription check
- `short_speech_with_silence.wav` — same speech bracketed by 3s silence at
  start and end, for VAD sidecar correctness
- `tiny_video.mp4` — ≤5s video with known audio, for extractor tests
- `golden/` — expected outputs (`.txt`, `.srt`, `.md`, `.json`) for each fixture

**Adapter-level stubs (no network in CI):**
- `tests/stubs/yt_dlp_stub.py` — fake downloader that returns a local fixture
- `tests/stubs/provider_stub.py` — fake `TranscriptionProvider` that returns
  a deterministic `TranscriptResult` and records retry attempts
- `tests/stubs/llm_stub.py` — fake LiteLLM response for summarize/clean tests

**Integration tests (opt-in, marked `@pytest.mark.integration`):**
- Hit the real `faster-whisper` model (runs locally, no network after prefetch)
- Real YouTube download, real Deepgram, real LLM call — all skipped unless
  `SSM_INTEGRATION=1` is set. CI runs only the unit lane; a separate
  manually-triggered workflow runs the integration lane.

**Determinism:**
- Pin `faster-whisper` to a minor version in `pyproject.toml` so transcript
  assertions don't drift across upgrades
- Golden-file tests use "contains expected words" assertions, not exact
  string equality, for the transcript itself; exact equality is fine for
  formatter output given a fixed `TranscriptResult`

#### F8. Observability (minimum viable)

- Use Python `logging` (not `print`) everywhere under `src/transcriber/`
  except the CLI presentation layer (which uses `rich.console`)
- Log level controlled by `TRANSCRIBER_LOG_LEVEL` (already in config stub)
- Never log secrets: the config module exposes `redacted_dump()` for any
  diagnostic output (replaces the current `settings.model_dump()` in the
  `config` command)
- Cache hits/misses, provider selection, and budget decisions are logged at
  `INFO`; raw transcripts stay at `DEBUG`

---

### Phase 1 — MVP: Transcribe a Local File (working end-to-end)

**Goal:** `uv run ssm-transcriber transcribe ./video.mp4` produces `./video.txt` with the transcript.

**Read first:** [Phase 1 Foundations](#phase-1-foundations-contracts-that-later-phases-depend-on) — F1–F8 are binding contracts. Phase 1 implements them; later phases only extend them.

Files to create/modify:
- `src/transcriber/sources/__init__.py` + `src/transcriber/sources/base.py` — `PreparedMedia` dataclass (F2) and `LocalSource` that returns one. No `resolve_source()` yet; the CLI wires `LocalSource` directly until Phase 2
- `src/transcriber/core/workspace.py` — `RunWorkspace` context manager (F5)
- `src/transcriber/core/audio_extractor.py` — `ffmpeg-python`: extract audio from video → 16kHz mono WAV **written into the run workspace**. Does NOT strip silence from the canonical path. Separately computes a VAD sidecar `speech_regions: list[tuple[float, float]]` on the original timeline (F-cost-section, item 3)
- `src/transcriber/core/transcriber.py` — `faster-whisper` wrapper: lazy singleton model loader, transcribes the **full** WAV, returns `TranscriptResult`. Exposes `model_id` and `model_revision` for the cache key
- `src/transcriber/core/cache.py` — versioned `CacheKey` composite (F3), atomic writes, `get` / `set`, schema-versioned directory layout
- `src/transcriber/core/models.py` — `download_model(quality)` helper + preflight check surfaced in the CLI (F6)
- `src/transcriber/config.py` — extend stub with `CACHE_DIR`, `CACHE_ENABLED`, `LOG_LEVEL`, `KEEP_TEMP`; add `redacted_dump()` (F8)
- `src/transcriber/cli.py` — wire `transcribe` to `LocalSource` → `RunWorkspace` → extractor → transcriber → cache → atomic output write. Add `ssm-transcriber models download` subcommand (F6). Replace `settings.model_dump()` in the `config` command with `redacted_dump()`

**Flow (sync, single `RunWorkspace`):**
```
CLI input (file path)
  ├─ open RunWorkspace (temp dir, try/finally cleanup)
  ├─ LocalSource.prepare(uri, workspace) → PreparedMedia
  ├─ audio_extractor.extract(media) → canonical WAV (full timeline) in workspace
  ├─ compute CacheKey (F3) from canonical WAV hash + settings + model revision
  ├─ cache.get(key) → hit? → atomic write output → exit ($0, no model load)
  ├─ audio_extractor.vad_sidecar(wav) → speech_regions for cost display only
  ├─ transcriber.transcribe(wav, language) → TranscriptResult
  ├─ cache.set(key, result)                [atomic]
  ├─ write output file via atomic rename   [F5]
  └─ workspace cleanup on exit (or keep if --keep-temp)
```

**Key implementation details:**
- `TranscriptResult` is a frozen dataclass: `full_text`, `segments` (list of `{start, end, text}` on the **original** timeline), `language`, `duration`, `speech_duration` (derived from the VAD sidecar), `model_id`, `model_revision`
- Quality-to-model mapping: `fast→tiny`, `balanced→base` (default), `best→large-v3`
- VAD is a **sidecar**, not a transform — the canonical transcription path never sees stripped audio. `speech_duration` is used only for cost display (Phase 5) and reduced uploads (Phase 5)
- Model loaded once per process via a module-level singleton; first call blocks on download with a clear progress line (F6)
- CLI output via `rich` progress spinner; show `Cache hit — skipped transcription` when applicable; log cache/budget decisions at `INFO` (F8)
- **Sync all the way through.** No `async def` anywhere in `src/transcriber/` in Phase 1 (F1)

**CLI interface:**
```bash
uv run ssm-transcriber transcribe ./interview.mp4
uv run ssm-transcriber transcribe ./podcast.mp3 --output ./notes.txt --quality best
uv run ssm-transcriber transcribe ./lecture.mp4 --quality fast --language en
uv run ssm-transcriber transcribe ./lecture.mp4 --no-cache   # force re-transcription
```

**Test fixtures required for Phase 1** (per F7):
- `tests/fixtures/short_speech.wav` — ≤10s real speech ("Hello, this is a transcription test")
- `tests/fixtures/short_speech_with_silence.wav` — same speech bracketed by 3s silence before and after, used to assert VAD sidecar correctness and timestamp fidelity
- `tests/fixtures/tiny_video.mp4` — ≤5s video with the same audio track, for extractor tests
- `tests/fixtures/golden/short_speech.txt` — expected text output (word-contains assertion, not equality)
- Commit all fixtures; total < 1MB

**Unit tests for Phase 1:**
- `tests/unit/test_cache.py` — `CacheKey` digest stability across runs; different `model_revision` / `language` / `vad_mode` produce different digests; schema version bump invalidates
- `tests/unit/test_workspace.py` — `RunWorkspace` cleanup on normal exit, exception, and simulated `SIGINT`; `--keep-temp` preserves
- `tests/unit/test_audio_extractor.py` — video → 16kHz mono WAV; VAD sidecar on `short_speech_with_silence.wav` returns regions matching the known speech window (±200ms)
- `tests/unit/test_transcriber.py` — uses `short_speech.wav`, asserts transcript contains expected words on the **original timeline** (segment start > 0 on the silence-bracketed fixture)
- `tests/unit/test_atomic_write.py` — interrupted write leaves no partial output file
- `tests/unit/test_config_redaction.py` — `redacted_dump()` does not leak API keys
- `tests/unit/test_local_source.py` — `LocalSource.prepare` returns a `PreparedMedia` whose `local_path` equals the input
- Phase 1 is not "done" until all unit tests pass locally AND in CI

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

**Goal:** `uv run ssm-transcriber transcribe "https://youtu.be/..."` works.

Files to create/modify:
- `src/transcriber/sources/youtube.py` — yt-dlp wrapper: download audio-only to temp dir, return local WAV path + metadata (title, duration)
- `src/transcriber/sources/local.py` — thin wrapper around local file (mirrors YouTube interface)
- `src/transcriber/sources/__init__.py` — `resolve_source(uri)`: returns correct source based on URI pattern (URL → YouTube, path → local)
- `src/transcriber/cli.py` — update `transcribe` to call `resolve_source()` first, then existing pipeline

**Source detection logic** (hostname match — see F2):
```python
from urllib.parse import urlparse
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

def resolve_source(uri: str) -> Source:
    try:
        host = urlparse(uri).hostname
    except ValueError:
        host = None
    if host in YOUTUBE_HOSTS:
        return YouTubeSource()
    return LocalSource()
```
Never match on `http://` / `https://` alone — that collides with Google Drive
(Phase 4) and any future hosted source. All sources return `PreparedMedia` per F2.

**Verification:** `uv run ssm-transcriber transcribe "https://youtu.be/dQw4w9WgXcQ"` produces a transcript.

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
uv run ssm-transcriber transcribe ./video.mp4 --format srt
uv run ssm-transcriber transcribe "https://youtu.be/..." --format md --output notes.md
```

**Verification:** All 4 output formats produce valid files.

---

### Phase 4 — Google Drive Source

**Goal:** `uv run ssm-transcriber transcribe "drive://FILE_ID"` works after auth.

Files to create/modify:
- `src/transcriber/sources/google_drive.py` — OAuth2 flow + `google-api-python-client` download
- `src/transcriber/cli.py` — add `transcriber auth google-drive` command for OAuth setup
- `src/transcriber/sources/__init__.py` — add `drive://` pattern to `resolve_source()`
- Add to `pyproject.toml`: `google-api-python-client`, `google-auth-oauthlib`

**Auth flow:**
```bash
uv run ssm-transcriber auth google-drive   # opens browser, saves token
uv run ssm-transcriber transcribe "drive://1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
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
- `src/transcriber/core/budget_router.py` — enforces the two-gate spend model (F4):
  - **Gate 1 (configured):** does the provider have a usable key/endpoint? (env var check)
  - **Gate 2 (allowed):** does the current budget permit paid use?
  - `free` → only `cost_per_minute == 0.0` providers are allowed, regardless of which keys are configured. Error with a clear message if a paid provider is explicitly requested
  - `low` → `faster_whisper` first; if `--quality best` and audio > 10 min, *suggest* Deepgram — user must confirm
  - `best` → paid providers become candidates; still requires cost confirmation
  - "Key exists" is never sufficient on its own. The router logs the chosen provider and the reason at `INFO`
- `src/transcriber/config.py` — add `TRANSCRIPTION_PROVIDER` (preferred, not mandatory), `DEFAULT_BUDGET` settings
- CLI: add `--budget free|low|best` flag (default: `free`); `--yes` skips only the interactive confirmation prompt — both Gate 1 (configured) and Gate 2 (allowed by budget/flags) are still enforced
- Cost estimate uses `speech_duration` from the VAD sidecar (not total media duration) so users see the billable figure
- Before any cloud call: print estimated cost and require confirmation unless `--yes`

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

**Verification:** `--budget free uv run ssm-transcriber transcribe ./audio.mp3` uses local only; cloud providers prompt for cost confirmation; simulated 429 triggers retry then success.

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

**LLM cost controls (per F4 — no silent paid fallback):**
- `--summarize` / `--clean` default to the free tier (Groq). They are **not** a paid-LLM opt-in on their own
- Falling back from Groq to any paid LLM requires **all three**: (a) paid key present, (b) `--allow-paid-llm` flag, (c) fresh cost confirmation at the prompt
- Without `--allow-paid-llm`, a Groq failure surfaces an error instead of silently escalating to Gemini/Claude/OpenAI
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
- `src/transcriber/agents/nodes.py` — one function per pipeline stage, returning `dict` of state updates. Nodes may be sync or async — that is isolated inside the graph (F1). The existing sync implementations from Phases 1–5 are wrapped, not rewritten
- `src/transcriber/cli.py` — `transcribe` command drives the graph. If any node is async, the CLI uses `graph.invoke()` / `graph.ainvoke()` as appropriate, but the CLI entry point itself stays sync with a single `asyncio.run()` wrapper at the boundary if needed

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
| GH | GitHub repo `manjunath84/SSM-Transcriber` | Remote origin, PR-based phase tracking |
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

## AI Coding Context and Workflow Strategy

The repo now uses three AI-facing layers:

1. **Source docs** — `docs/PLAN.md` owns technical contracts and
   `docs/learn/README.md` owns living-doc / teaching-register rules.
2. **Root tool adapters** — `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`,
   `.cursorrules`, and `.github/copilot-instructions.md` keep the few inline
   guardrails an AI needs before it can safely start.
3. **Workflow docs** — `docs/ai/README.md` routes tools to the right source
   docs, and `docs/ai/runbooks/` holds checklist-heavy workflows. Claude Code
   may load those runbooks through `.claude/commands/`.

Rules for maintaining this stack:

- Do not create a second technical source of truth outside `docs/PLAN.md`
- Keep root adapters compact but self-sufficient; a tool should not need a
  first-turn file read just to avoid obvious mistakes
- Keep workflow-heavy prompts in runbooks, not in always-loaded tool files
- When rules change, update the source docs first and then align adapters and
  runbooks

---

## Verification (End-to-End Test per Phase)

- **GitHub setup:** `gh repo view manjunath84/SSM-Transcriber` shows the repo; `git remote -v` shows `origin`
- **Phase 0:** `uv run ssm-transcriber --help` shows commands
- **Phase 0.5:** CI green on PR #1; `uv.lock` tracked; Python 3.12 venv; all internal env vars prefixed `TRANSCRIBER_`; PR merged to `main`
- **Phase 1:** `uv run ssm-transcriber transcribe tests/fixtures/short_speech.wav` → correct transcript; unit tests pass; CI green
- **Phase 2:** `uv run ssm-transcriber transcribe "https://youtu.be/..."` → transcript file
- **Phase 3:** `uv run ssm-transcriber transcribe short.wav --format srt` → valid SRT file
- **Phase 4:** `uv run ssm-transcriber auth google-drive && uv run ssm-transcriber transcribe "drive://ID"` → transcript
- **Phase 5:** `TRANSCRIBER_TRANSCRIPTION_PROVIDER=deepgram uv run ssm-transcriber transcribe short.wav` → Deepgram transcript with cost prompt
- **Phase 6a:** `uv run ssm-transcriber transcribe short.wav --summarize` → transcript + summary via Groq free tier
- **Phase 6b:** Same as 6a but now running through LangGraph; graph visualization shows all nodes

## Cross-phase practices (apply at the end of every phase)

1. **README roadmap checkbox** — tick off the completed phase in `README.md` before opening the PR
2. **CI must be green** — no phase merges until ruff, mypy, and pytest all pass on the PR
3. **AI workflow docs updated** — update any affected source docs, adapters,
   runbooks, or command files when the current phase or workflow conventions
   change; if a layer needed no update, note that explicitly in the PR
4. **Phase branch deleted after merge** — keep the branch list clean
