# Requirements — Drive Source (URL Passthrough)

## Goal

Ship a second source for SSM-Transcriber: take a Google Drive file the
user has already shared as "anyone with link can view," and feed its
public download URL straight to AssemblyAI's `audio_url` ingestion —
**no OAuth, no local download, no upload**. The user runs
`uv run ssm-transcriber transcribe "drive://FILE_ID" --title "Session N" --budget low -y`
or pastes the full Drive URL from their browser; the existing Slice 1
output (enriched Markdown + YAML frontmatter) lands the same way as for
local files.

This slice exists because the author has a Drive folder of educational
sessions that are already shared as anyone-with-link, and downloading
each one to local disk before transcription is a 5–10× wall-clock
multiplier (download bandwidth + upload bandwidth) compared to
AssemblyAI's server-to-server fetch. The single working `curl` the
author has already validated against AssemblyAI is the
implementation's reference call.

## Non-goals

Each item below is explicitly out of scope for this slice and lands later:

- **OAuth / private Drive files.** Slice 3. PLAN.md Phase 4's
  `auth google-drive` flow stays unwritten in this slice; the
  `TRANSCRIBER_GOOGLE_*` slots in `.env.example` stay reserved.
- **Drive folder traversal.** Folder listing requires Drive API access
  (= OAuth). Defer to Slice 3 alongside private-file support.
- **Drive metadata in frontmatter** (file owner, modified time,
  permissions). Same OAuth dependency.
- **Auto-derived title from Drive filename via Content-Disposition
  scrape.** Defer; `--title` flag covers the user-facing need today.
- **Cost pre-estimation for Drive sources.** Skipped per the brainstorm
  decision; the message tells the user AssemblyAI bills per-minute and
  exact cost is in the dashboard. No `ffprobe-over-HTTP` or HEAD-based
  bitrate heuristic in this slice.
- **YouTube source.** Phase 2.
- **Other cloud providers** (Deepgram, OpenAI Whisper, Hugging Face).
  Phase 5.
- **Concurrent runs.** Single-user CLI; same as Slice 1.

## Scenarios / user flows

1. **Happy path — full Drive URL.** User pastes from browser:
   `uv run ssm-transcriber transcribe "https://drive.google.com/file/d/1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd/view" --title "Session 17" --budget low -y`.
   Tool parses the file ID, builds the public-download URL, prints the
   AssemblyAI job ID, polls until done, writes
   `./output/Session-17-2026-05-04.md`. Exit `0`.
2. **Happy path — `drive://FILE_ID` form.** Same flow with
   `transcribe drive://1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd --title "Session 17" --budget low -y`.
   Identical output to scenario 1.
3. **No `--title` flag.** Output filename and frontmatter `title`
   fall back to the file ID
   (`1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd-2026-05-04.md`,
   `title: 1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd`). Ugly but works.
4. **Default budget rejection.** User omits `--budget`. Tool exits `2`
   with: "AssemblyAI is a paid provider ($0.009/min). Current budget is
   `free`. Rerun with `--budget low` (or `--budget best`)." (Same as
   Slice 1 — Drive doesn't change Gate 2.)
5. **Missing API key.** `--budget low` but no `ASSEMBLYAI_API_KEY` in
   `.env`. Tool exits `2` with the existing Gate 1 message. (Same as
   Slice 1.)
6. **Drive cost-estimate skip.** Both gates pass. Instead of a numeric
   estimate, tool prints: "AssemblyAI is billing per-minute against URL
   passthrough; the exact cost will be visible in the AssemblyAI
   dashboard after the run." Confirmation prompt fires unless `-y`.
7. **Invalid Drive URL** (`drive://`, no ID; `drive://invalid_id`).
   Tool exits `2` with a clear "could not extract a Drive file ID from
   `<input>`" message.
7a. **Non-Drive URL** (`https://example.com/notfound`,
    `https://youtube.com/...`). Tool exits `2` with: "URI scheme not
    supported. Expected: a local file path, `drive://FILE_ID`, or a
    Google Drive URL (`https://drive.google.com/...`)." This is a
    *dispatch-layer* rejection (not a `LocalSource` "file not found"
    fallthrough) — if the user typed `://`, they meant a URL, not a
    file path.
8. **AssemblyAI 4xx for the URL** (file isn't actually shared as
   anyone-with-link, or sharing was revoked). AssemblyAI returns a 4xx
   from `/transcript`; existing `ProviderError` handling surfaces it as
   exit `3`. Message includes the AssemblyAI status text so the user
   knows to check sharing.
9. **AssemblyAI polling returns `error` status** (e.g. it failed to
   fetch the URL after retries). Existing polling-error handling
   surfaces the AssemblyAI error message to the user; exit `3`.
10. **User Ctrl-C during polling.** Workspace cleanup runs; job ID was
    printed at start so the user can recover from the AssemblyAI
    dashboard. (Same as Slice 1.)

## Constraints and decisions

### From the constitution (binding)

Per `specs/tech-stack.md` and `docs/PLAN.md`:

- **Sync only.** No `async def` introduced.
- **Config boundary.** `from transcriber.config import settings` outside
  `config.py`; the only `os.getenv("ASSEMBLYAI_API_KEY")` calls remain
  inside `config.py` and `providers/assemblyai.py`'s `_api_headers`.
  This slice adds zero new env-var reads.
- **Two-gate spend.** Gate 1 (key configured) and Gate 2
  (`--budget != "free"`) still fire for Drive sources. The pre-estimate
  number is the only thing skipped; the gates that prevent accidental
  spend are unchanged.
- **Atomic write.** Output goes to `<dest>/<output>.tmp` →
  `os.replace()`, in the destination directory.
- **`RunWorkspace`.** Per F5 — created even when there's no local file
  to extract; the workspace is still the lifetime owner for any
  per-run state, kept consistent with Slice 1.
- **tenacity retry.** Same policy on the new `audio_url` POST as on the
  existing `_create_transcript` call (3 attempts, 1s/2s/4s backoff,
  retry on 429/502/503/504/timeout/connection only).
- **Logging.** `logging` for library code; `rich` only in the CLI
  layer. No `print()` in library code.
- **Vendor API calls — verbatim copy.** Per the CLAUDE.md guardrail
  added in PR #13, the `audio_url` request body shape is copied
  byte-for-byte from the §"Reference calls (verbatim)" section below.
- **HTTP mocks must use body-shape matchers.** Per the same PR-#13
  guardrail. Every new mock uses `responses.matchers.json_params_matcher`.

### Feature-specific decisions (from this session's brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Auth model | **Public URL passthrough only.** No OAuth, no token files, no `google-api-python-client`. | Matches the user's working `curl`. The user's actual workflow today is "share Drive video as anyone-with-link, then transcribe" — passthrough costs zero new code surface vs OAuth. PLAN.md's Phase 4 OAuth flow lands as Slice 3 when private-file support is needed. |
| URL forms accepted | **Both `drive://FILE_ID` and full Drive URL.** | Humans paste full URLs from the Drive browser UI; scripts use `drive://`. Both round-trip to the same file ID under ~10 lines of regex parsing. |
| Frontmatter `title` source | **`--title <str>` flag, defaults to file ID.** | No OAuth = no programmatic filename access. Honest about the constraint; user knows the title at invocation time anyway. Auto-scraping Content-Disposition deferred (>100 MB Drive interstitial breaks the simple-HEAD approach). |
| Output filename | **`{title-or-file-id}-{YYYY-MM-DD}.md`** in `settings.output_dir`. Whitespace in title → `-`; other characters round-trip. Suffix increment on collision (existing). | Matches Slice 1's pattern; `--output` override works too. |
| Cost pre-estimation | **Skipped for Drive sources.** Notify message: "AssemblyAI bills per-minute against URL passthrough; exact cost in dashboard." Soft cap silenced. Both hard gates still fire. | No local file → no `ffprobe`. `ffprobe`-over-HTTP fails on Drive's >100 MB interstitial; HEAD + bitrate heuristic is wildly inaccurate (same file size, very different durations). Honest "no estimate" beats wrong number. |
| `PreparedMedia` extension | Add **`remote_url: str \| None = None`**. Make `local_path: Path \| None`. Validation: exactly one must be set. | Smallest change to F2 that supports both upload and passthrough. Provider branches once on `if media.remote_url`. Backward-compatible because new field is keyword-only with a default. |
| Provider dispatch | Provider's `transcribe()` checks `media.remote_url`; if set, POST `/transcript` with `audio_url=media.remote_url` (skips upload entirely); else existing upload flow. | Single branch, ~10 lines. Polling, retry, formatter all reused unchanged. |
| Workspace lifecycle for Drive sources | **Still create one** per CLI invocation (per F5), even though there's no audio.wav to extract. | Keeps the lifecycle invariant; allows future debugging artifacts (e.g. saved request bodies) to land somewhere consistent without touching the contract. |
| New CLI flags | **`--title <str>`** only. No new auth flag, no new source flag. | YAGNI for OAuth and folder traversal. |
| Where the output frontmatter `source_uri` points | **`drive://FILE_ID`** (canonical form), regardless of which URL form the user passed. | Single canonical recordable form; user's pasted Drive-browser URL contains `/view` clutter that doesn't round-trip cleanly. |
| Exit codes | Same matrix as Slice 1: `0` success or user-declined; `2` config (Gate 1, Gate 2, bad URL, unparseable input); `3` provider (AssemblyAI 4xx, polling timeout, retry exhaustion); `4` local error (output write failure). No new code introduced. | |

## Reference calls (verbatim)

> **Required per PR #13's guardrail.** The implementation copies these
> calls byte-for-byte; never paraphrase from memory.

### AssemblyAI — `POST /v2/transcript` with `audio_url` (URL passthrough)

**Source:** user-supplied; user verified this exact call against the
real AssemblyAI API earlier in the brainstorm session.
**Retrieval date:** 2026-05-04
**Vendor docs:** https://www.assemblyai.com/docs/pre-recorded-audio/transcribe-an-audio-file

```bash
curl https://api.assemblyai.com/v2/transcript \
  -H "authorization: <ASSEMBLYAI_API_KEY>" \
  -H "content-type: application/json" \
  -d '{
    "audio_url": "https://drive.google.com/uc?export=download&id=1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd",
    "speech_models": ["universal-3-pro"],
    "speaker_labels": true
  }'
```

The response shape and the polling flow that follows are identical to
the existing `_create_transcript` → `_get_transcript` cycle in
`src/transcriber/providers/assemblyai.py`. The single new wire-shape
fact this slice introduces is: **when `audio_url` is provided, the
`/upload` endpoint is NOT called — AssemblyAI fetches the URL itself.**

### Google Drive — public download URL form

**Source:** user-supplied (worked verbatim against AssemblyAI when used
as `audio_url` above).
**Retrieval date:** 2026-05-04

```text
https://drive.google.com/uc?export=download&id=<FILE_ID>
```

For files >100 MB Drive serves an HTML interstitial ("Google Drive
can't scan for viruses") on the first hit. **AssemblyAI handles this
interstitial automatically when fetching `audio_url`** (verified
implicitly by the fact that the user's reference `curl` works against a
file in this size range). This slice does not need to handle the
interstitial in our own code — we never download the file ourselves.

### Drive URL forms the parser must accept

```text
drive://1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd
https://drive.google.com/file/d/1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd/view
https://drive.google.com/file/d/1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd/view?usp=sharing
https://drive.google.com/open?id=1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd
https://drive.google.com/uc?export=download&id=1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd
```

All five round-trip to the same file ID `1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd`.

## Output contracts

The markdown frontmatter for Drive sources uses the exact same schema
as Slice 1, with these field-level rules:

```yaml
title: <--title value, or file ID if --title not passed>
source_uri: drive://<FILE_ID>      # canonical, regardless of input form
source_kind: google_drive
duration_seconds: <float, from AssemblyAI's audio_duration in the response>
language: <ISO code, from AssemblyAI's language_code>
provider: assemblyai
model: <universal-3-pro|universal-2>
diarized: <bool>
speakers: <int or null>
assemblyai_job_id: <string>
created: <YYYY-MM-DD>
```

`duration_seconds` for Drive sources comes from AssemblyAI's response,
not local `ffprobe`. The frontmatter shape is otherwise identical to
Slice 1's; this means downstream consumers (Obsidian, NotebookLM, the
`knowledge-base` repo's distill workflow) treat both source types
uniformly.

## F-contract status

| Contract | Status in Slice 2 | Notes |
|---|---|---|
| F1 — sync model | implemented | No `async def` introduced. |
| F2 — `PreparedMedia` | **extended** (additively) | `local_path` becomes `Path \| None`; new `remote_url: str \| None` field. Validation: exactly one set. Backward-compatible — `LocalSource` still constructs `PreparedMedia` the same way. |
| F3 — versioned cache key | **deferred** | Same as Slice 1; re-runs re-pay. |
| F4 — two-gate spend | implemented (extended) | Both gates fire on Drive sources; only the cost-estimate number is skipped (replaced with the "no pre-estimate available" notify message). Soft cap silenced for Drive only. |
| F5 — `RunWorkspace` | implemented | Workspace still created per run for lifecycle consistency, even when no audio file is extracted. |
| F6 — model preflight | **deferred** | Only matters for `faster-whisper` (Phase 1 MVP). |
| F7 — fixtures | partial | New mocked-HTTP cases for the URL-passthrough path; new manual-runbook step for one real Drive URL. No real Drive fixture in CI. |
| F8 — logging | implemented | `logger.info` for the URL the provider is fetching; `logger.info` for the job ID; existing logging patterns. |

## Dependencies added

Runtime: **none.**
Dev: **none.**

The public Drive download URL is a plain string we hand to AssemblyAI
in the existing `/transcript` POST. No `requests.get` against Drive
itself. No `google-api-python-client`, no `google-auth-oauthlib` (those
land in Slice 3).

`.env.example` requires no change. The `TRANSCRIBER_GOOGLE_CLIENT_SECRETS_FILE`
and `TRANSCRIBER_GOOGLE_TOKEN_FILE` slots already documented in
`.env.example` (lines 35-36) stay reserved for Slice 3.
