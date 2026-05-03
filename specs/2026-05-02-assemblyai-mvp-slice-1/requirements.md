# Requirements — AssemblyAI MVP Slice 1

## Goal

Ship the first working vertical slice of SSM-Transcriber: take a local audio
or video file, transcribe it via the **AssemblyAI** cloud provider (paid,
opt-in), and write a Markdown file containing the transcript plus a
general-purpose YAML frontmatter block.

This slice exists to validate the **paid-provider plumbing end-to-end**
(two-gate spend, retry, polling, atomic write, frontmatter shape) on a
30-second WAV before the Drive source loop adds OAuth complexity on top, and
before the broader Phase 1 / 3 / 5 work is generalized across providers and
formatters.

## Non-goals

Each item below is explicitly out of scope for this slice and lands later:

- **Google Drive source.** Slice 2.
- **YouTube source.** Phase 2.
- **`faster-whisper` local provider.** Phase 1 MVP — this slice is
  AssemblyAI-only and therefore *paid-only* by definition.
- **Other formatters: txt, srt, json.** Phase 3.
- **Other cloud providers: Deepgram, OpenAI Whisper, Hugging Face.** Phase 5.
- **LLM derivatives** (summary, action items, chapters via LeMUR). Phase 6a.
- **F3 versioned cache.** No caching in Slice 1; re-runs always re-pay.
- **F6 model preflight.** Only relevant once `faster-whisper` is wired.
- **VAD-derived `speech_duration` cost estimates.** Use raw `ffprobe`
  duration; document the imprecision.
- **Real AssemblyAI calls in CI.** Real calls live only in a manual runbook.
- **Concurrent runs / multi-user safety.** Single-user CLI; not designed for
  concurrent invocations against the same source file.

## Scenarios / user flows

1. **Happy path.** User runs `uv run ssm-transcriber transcribe ./interview.mp4 --budget low -y`. Tool extracts audio, prints the AssemblyAI job ID, polls until done (~real-time × 0.3), writes Markdown to `./output/interview-2026-05-02.md`, prints the final path. Exit `0`.
2. **Default budget rejection.** User omits `--budget`. Tool exits `2` with: "AssemblyAI is a paid provider ($0.009/min). Current budget is `free`. Rerun with `--budget low` (or `--budget best`)."
3. **Missing API key.** User has `--budget low` but no `ASSEMBLYAI_API_KEY` in `.env`. Tool exits `2` with: "AssemblyAI key not configured. Add `ASSEMBLYAI_API_KEY=...` to `.env` (see `.env.example`)."
4. **Re-run same file same day.** Output `interview-2026-05-02.md` already exists → tool writes `interview-2026-05-02-2.md`, then `-3`, etc. (suffix increment).
5. **High-cost confirmation.** User runs against a 90-min file. Estimated cost ≈ $0.81 — under the $5 soft cap, normal prompt. User runs against a 9-hour file. Estimated cost ≈ $4.86 — still under $5. User runs against a 12-hour podcast. Estimated cost ≈ $6.48 — soft cap fires, louder warning printed; standard `Proceed?` still asked; `--yes` still bypasses.
6. **Diarized multi-speaker.** Default behavior. Output body uses `**Speaker A:**` / `**Speaker B:**` prefixes per AssemblyAI utterance.
7. **Solo content.** User passes `--no-speakers`. Speaker prefixes omitted; utterances run together as paragraphs.
8. **AssemblyAI 429 transient.** First HTTP call returns 429; tenacity retries with exp backoff (1s/2s/4s); third attempt succeeds; user sees no error.
9. **AssemblyAI 401 permanent.** Auth fails; no retry (4xx other than 429); exit `3` with "AssemblyAI auth failed; check `ASSEMBLYAI_API_KEY`."
10. **Polling wall-clock timeout.** Job not done after 30 min wall clock. Tool exits `3` with the job ID and a hint to recover via the AssemblyAI dashboard.
11. **User declines confirmation.** User runs without `-y`, sees the cost prompt, types `n`. Exit `0` cleanly with no charge incurred.

## Constraints and decisions

### From the constitution (binding)

Per `specs/tech-stack.md` and `docs/PLAN.md`:

- **Sync only.** No `async def` in this slice's code paths.
- **Config boundary.** `from transcriber.config import settings` everywhere outside `config.py`; the only `os.getenv("ASSEMBLYAI_API_KEY")` call lives *inside* `config.py` (exposed as a `bool` property for Gate 1).
- **Two-gate spend.** Gate 1 = key configured; Gate 2 = `--budget != "free"`. Default `--budget free` blocks AssemblyAI even when the key is present.
- **Atomic write.** Write `<output>.tmp` *in the destination directory* (not `/tmp`), then `os.replace()`. Crash mid-write must not leave a half-written `.md` and must not destroy any pre-existing file at the same path.
- **`RunWorkspace`.** One temp dir per CLI invocation; cleaned up on `__exit__` unless `--keep-temp` is set.
- **tenacity retry.** 3 attempts max, exponential backoff 1s / 2s / 4s, retry on 429 / 503 / network timeouts only, never on other 4xx.
- **Logging.** `logging` for library code; `rich` only in the CLI presentation layer. No `print()` in library code.
- **Secrets.** Never log full settings or API keys.

### Slice-specific decisions (from this session's brainstorming + Q&A)

| Decision | Choice |
|---|---|
| Why AssemblyAI is the first hosted provider | **Convenience** (the explicit mission tiebreaker per [`specs/mission.md`](../mission.md)). The author has ~$60 of existing AssemblyAI credit and wants to utilise it first. This slice does **not** claim AssemblyAI is the most accurate or cheapest provider; per the mission, the long-term provider set is determined by future head-to-head accuracy + cost evaluations, with accuracy as the primary tiebreaker. AssemblyAI was simply the most convenient one to ship the paid-provider plumbing against first. |
| Default output path | `{settings.output_dir}/{stem}-{YYYY-MM-DD}.md`. `output_dir` defaults to `./output` from the existing `TranscriberSettings`. |
| Filename collision | Suffix increment: `-2`, `-3`, etc. Never overwrites. |
| Speaker diarization | ON by default (free or near-free on AssemblyAI; harder to add after the fact than to ignore). `--no-speakers` to disable. |
| Per-utterance timestamps | ON by default (`[mm:ss]` prefix). `--no-timestamps` to strip. |
| Speech model | `universal-3-pro` by default. `--model universal-3-pro\|universal-2` flag. (Originally specced as `best`/`nano`; AssemblyAI retired those shorthands during implementation — see fix commit `46ccaa1`.) |
| Soft cost cap | $5. Above this, print a louder warning before the standard confirmation prompt. `--yes` still bypasses the prompt (consistent with smaller jobs). |
| AssemblyAI job ID | Print at start of polling AND embed in markdown frontmatter as `assemblyai_job_id`. Cheap insurance against Ctrl-C and crashes. |
| Polling cap | 30 min wall clock. `--max-wait MINUTES` overrides. |
| `--keep-temp` flag | User-visible, default off. Useful for debugging the extracted WAV. |
| Cost estimate basis | Raw `ffprobe` duration (not VAD `speech_duration` — F3 cache and VAD sidecar both deferred). Documented as upper bound. |
| Exit codes | `0` success or user-declined; `2` config error (missing key, wrong budget, bad source path); `3` provider error (401, exhausted retries, polling timeout, job error); `4` local error (ffmpeg missing/failed, file not readable, disk full). |

### Output frontmatter contract

The markdown file is the user-facing deliverable. Its YAML frontmatter has
this fixed schema (general-purpose; deliberately *not* the
`knowledge-base` repo's closed schema, since transcripts feed into the
human-curated distill workflow downstream):

```yaml
title: <input filename without extension>
source_uri: file:///<absolute path>
source_kind: local
duration_seconds: <float, from ffprobe>
language: <ISO code>
provider: assemblyai
model: <universal-3-pro|universal-2>
diarized: <bool>
speakers: <int or null>
assemblyai_job_id: <string>
created: <YYYY-MM-DD>
```

Field order is stable across runs (sortable diffs).

### F1–F8 contracts: this slice's status

| Contract | Status in Slice 1 | Notes |
|---|---|---|
| F1 — sync model | implemented | No `async def` introduced. |
| F2 — `PreparedMedia` | implemented (minimal) | Just enough for `LocalSource`; `extra` field used minimally. |
| F3 — versioned cache key | **deferred** | No caching; re-runs re-pay. |
| F4 — two-gate spend | implemented (minimal) | Hardcoded around AssemblyAI; full provider-abstraction generalization stays in Phase 5. |
| F5 — `RunWorkspace` | implemented | |
| F6 — model preflight | **deferred** | Only matters once `faster-whisper` is wired. |
| F7 — fixtures | partial | Mocked HTTP for provider; golden markdown for formatter; manual real-API runbook. No CI fixtures requiring real audio. |
| F8 — logging | implemented | `logging` everywhere; `rich` only in CLI. |

### Dependencies added

Runtime: `assemblyai>=0.30.0`, `tenacity>=8.2.0`.
Dev: `responses>=0.25.0` (mocked HTTP for unit tests).

`pyproject.toml` already has `ffmpeg-python`, `typer`, `rich`,
`pydantic-settings`. `.env.example` already has the
`ASSEMBLYAI_API_KEY=` slot at line 45 — no `.env.example` change needed.
