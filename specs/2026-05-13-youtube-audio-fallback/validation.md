# Validation — YouTube Source (yt-dlp Audio Fallback)

## Success criteria

The slice ships when all of the following are true:

1. **Captioned videos behave identically to Slice 1.** Zero behavioural
   regression on the captions path: same output bytes for a video
   whose captions were available before this slice. Validated by
   re-running PR #31's manual e2e (the RAG-Explained Shorts URL or
   equivalent captioned video).

2. **Captionless videos on `--budget low+` produce a usable
   transcript.** End-to-end run against a real captionless YouTube
   Shorts URL: probe → cost prompt → confirm → yt-dlp download →
   `extract_audio` → AssemblyAI → markdown written. Exit 0.

3. **Captionless videos on `--budget free` exit cleanly.** Exit 2
   with the budget-aware no-captions message. No yt-dlp probe, no
   download, no AssemblyAI call. Wall time < 5s (just the captions
   library round-trip + decision).

4. **Frontmatter contract holds.** For an audio-fallback output:
   `source_kind: youtube_audio`, `source_uri: https://youtu.be/<ID>`
   (NOT `file://`), `provider: assemblyai`, `model` populated,
   `assemblyai_job_id` populated, `caption_type` field absent.

5. **Exit-code matrix is correct.** Each row of the matrix in
   `plan.md` §4c is exercised by a test (parametrized) and produces
   the expected exit code.

6. **No silent fallback on the wrong exceptions.** The 5 non-trigger
   captions exceptions (`VideoUnavailable`, `VideoUnplayable`,
   `InvalidVideoId`, `AgeRestricted`, `PoTokenRequired`) preserve
   Slice 1's error messages and exit codes verbatim. Audio path is
   never invoked for these.

## Test cases

### Unit — `prepare()` (captions arm)

| # | Scenario | Expected |
|---|---|---|
| 1 | Captions available | `prepare()` returns `PreparedTranscript`; no yt-dlp call |
| 2 | `TranscriptsDisabled` raised by captions library | `prepare()` raises `NoCaptionsAvailable` (with original exception in `__cause__`) |
| 3 | `NoTranscriptFound` raised by captions library | `prepare()` raises `NoCaptionsAvailable` (with original exception in `__cause__`) |
| 4 | `VideoUnavailable` raised | Propagates; **NOT** wrapped in `NoCaptionsAvailable` |
| 5 | `VideoUnplayable` raised | Propagates; **NOT** wrapped |
| 6 | `InvalidVideoId` raised | Propagates; **NOT** wrapped |
| 7 | `AgeRestricted` raised | Propagates; **NOT** wrapped |
| 8 | `PoTokenRequired` raised | Propagates; **NOT** wrapped |
| 9 | `IpBlocked` raised | Propagates; **NOT** wrapped |
| 10 | `YouTubeRequestFailed` raised | Propagates; **NOT** wrapped |
| 11 | Network exhaustion (`requests.RequestException`) | Propagates; **NOT** wrapped |

### Unit — yt-dlp probe

| # | Scenario | Expected |
|---|---|---|
| 12 | Probe returns title + duration | Fields read; PreparedMedia gets title from probe |
| 13 | Probe raises `ExtractorError` | Exception propagates with full message |
| 14 | Probe raises `GeoRestrictedError` | Exception propagates (subclass of `ExtractorError`) |
| 15 | Probe raises `DownloadError` (network) | Exception propagates after internal retries |
| 16 | `ydl_opts` shape matches `requirements.md` reference call | Byte-for-byte equality on the dict keys + values |

### Unit — yt-dlp download

| # | Scenario | Expected |
|---|---|---|
| 17 | Download succeeds | File on disk at workspace path; PreparedMedia.local_path points to it; `duration_seconds == float(probe.duration)`; `extra["probe_duration"] == str(probe.duration)` (asserts the `dict[str, str]` stringification — locks in one of the Codex-pass fixes) |
| 18 | Download raises `DownloadError` (network after retries) | Exception propagates |
| 19 | Download raises `PostProcessingError` (ffmpeg fail) | Exception propagates |
| 20 | Download raises `OSError` (disk full simulation) | Exception propagates |
| 21 | Downloaded file extension is whatever yt-dlp picked (m4a/opus/webm) | Test doesn't hard-code; reads `info["requested_downloads"][0]["filepath"]` |

### Unit — CLI exit-code matrix

Parametrized test `test_yt_dlp_exception_matrix`:

| # | Exception | Budget | Expected exit | Message snippet contains |
|---|---|---|---|---|
| 22 | `GeoRestrictedError` | low | 2 | "geo-restricted" |
| 23 | `UnavailableVideoError` | low | 2 | "unavailable for download" |
| 24 | `UnsupportedError` | low | 2 | "not supported by yt-dlp" |
| 25 | `ExtractorError` with "age-restricted" in msg | low | 2 | "requires authentication" |
| 26 | `ExtractorError` generic | low | 2 | "audio extraction failed" |
| 27 | `DownloadError` with "network" in msg | low | 3 | "network failure" |
| 28 | `DownloadError` generic | low | 3 | "audio download failed" |
| 29 | `PostProcessingError` | low | 4 | "ffmpeg failed" |
| 30 | `OSError` | low | 4 | "local I/O error" |
| 30b | `ProbeDurationUnknown` (probe returned `None` or `<=0`) | low | 2 | "could not determine video duration" |

### Unit — CLI integration with Slice 1 flow

| # | Scenario | Expected |
|---|---|---|
| 31 | Captioned video + `--budget free` | Captions path; output written; $0 |
| 32 | Captionless video + `--budget free` | Exit 2; no probe attempted; budget-aware error message |
| 33 | Captionless video + `--budget low` + user declines | Probe runs; prompt shown; user types "n"; exit 0; no download |
| 34 | Captionless video + `--budget low` + user confirms | Full flow; output written; **exactly one** budget prompt fires (no double-prompt regression from §4e bypass) |
| 35 | Captionless video + `--budget low -y` | Prompt skipped; full flow; output written |
| 36 | Captionless video + `--budget low` + `--upload-to-drive` | Full flow + Drive upload (shared render+write+upload block) |
| 37 | Captionless video + `--budget low` + `--upload-to-drive` + no folder configured | Exit 2 pre-flight (existing Slice 1/2.5 contract) |
| 37b | Local file + `--budget low` (regression check) | `kind=local` still hits the post-extract budget_check exactly once — Slice 1 contract for non-YouTube paths preserved |

### Unit — formatter

| # | Scenario | Expected |
|---|---|---|
| 38 | Render `youtube_audio` frontmatter | `source_kind: youtube_audio`, `source_uri: https://youtu.be/<ID>` (NOT `file://`), `provider: assemblyai`, `model` populated, NO `caption_type` field |
| 39 | Render `youtube_audio` body summary | Uses `<provider>/<model>` shape (e.g., `assemblyai/universal-3-pro`); NOT `youtube-captions (...)` |
| 40 | Frontmatter field order | Same canonical order as Slice 1 + assemblyai_job_id populated for this path |

## Edge cases / what could break

### Captions library disagrees with yt-dlp

A video where the captions library reports captions exist but the
chosen track is empty (zero segments). Slice 1 wouldn't raise
`NoTranscriptFound` — it'd return an empty transcript and the
markdown body would be empty under `## Transcript`. Slice 2 doesn't
change this. **Not handled.** Document as a known edge case; if
real users hit it, a future slice can either filter empty tracks
at the resolver or auto-fall through to audio.

### yt-dlp probe succeeds but download fails

The cost prompt fires, user confirms, then yt-dlp fails mid-download
(network drop, rate limit). The cost prompt was based on probe duration
— the user authorised spend that won't materialise (no AssemblyAI
call). The error message must make clear that **no charge occurred**
(consistent with the existing `BudgetError` and Drive-passthrough
"Cancelled by user; no charge incurred" message). Update the audio-
fallback `_handle_yt_dlp_exception` to emit "no charge incurred" for
exit-3 / exit-4 errors (cost-side reassurance).

### yt-dlp's duration field is None or 0

For some edge cases (live streams that haven't started, malformed
metadata) `info["duration"]` can be `None` or `0`. Cost estimate
math would produce `$0.00` and the prompt would silently lie
("Audio fallback would cost ~$0.00"). **Defence:** if probe returns
`duration is None or duration <= 0`, raise a custom
`ProbeDurationUnknown` exception → exit 2 with "could not determine
video duration from yt-dlp probe; the audio fallback can't show a
reliable cost estimate without duration. This usually means the
video is a live stream or premiere — not currently supported." This
slots into the exit-code matrix as a new row.

### Workspace cleanup vs. mid-download failure

If yt-dlp downloads a partial file and then raises, `RunWorkspace`'s
cleanup-on-exit handles the leftover. Already a contract today; no
new code. Test that workspace contents are gone after exit (existing
patterns suffice).

### Probe + download share the same `noplaylist` defence

`_extract_video_id` already rejects playlist URLs at parser level,
but `noplaylist=True` in both yt-dlp calls is defence-in-depth — if
a single-video URL somehow expands into a playlist (yt-dlp's URL
resolution can be surprising), we want it to NOT silently start
downloading multiple videos. Verify in tests that `noplaylist=True`
is present in `_YDL_OPTS_BASE`.

### yt-dlp version drift

`yt-dlp>=2024.1.0` is the only pin in `pyproject.toml`. Versions
ship every 1–2 weeks; behaviour of `extract_info` is generally
stable but format selection logic occasionally changes. The
slice's tests mock yt-dlp at the `YoutubeDL` boundary, so version
drift doesn't break unit tests. Manual e2e is the only thing that
catches it; if the e2e starts failing post-upgrade, the
`pyproject.toml` pin gets tightened in a small follow-up PR.

### Concurrent probe + download

The current pipeline is sync. yt-dlp's probe and download are two
separate `YoutubeDL` instances — no concurrency. Slice does not
introduce async (the F1 contract is sync through Phase 4 per
CLAUDE.md guardrails).

### `--language` flag on audio fallback

Slice 1 ignores `--language` for captions (track language is what
it is). For the audio path, `--language` is meaningful — it's an
AssemblyAI hint. Existing local-file flow passes `--language` to
the provider call; the audio-fallback path reuses that flow, so
`--language` flows through naturally. **Test:** captionless video
+ `--budget low` + `--language es` → AssemblyAI request body has
`language_code: "es"`. Don't ignore `--language` on the audio arm
the way we did on the captions arm.

### Title resolution when probe `info["title"]` is missing

Defence-in-depth: probe should always return `title` for a valid
video, but if it doesn't, the formatter's `_resolve_title` already
falls back to `media.extra["video_id"]` (Slice 1 contract). The
audio path sets `extra["video_id"]` so the fallback works. Verify
in a test that a probe response with `title=None` produces a
filename derived from the video ID, not `untitled-DATE.md`.

## Definition of done

A PR for this slice is mergeable when:

- All 40 test cases above pass under `uv run pytest`
- `uv run ruff check src/ tests/` exits 0
- `uv run mypy src/ tests/` exits 0
- `tests/manual/end_to_end.md` has a new section showing a real
  captionless YouTube Shorts URL run with output frontmatter
  pasted in (proof the e2e works, not just the unit tests)
- Slice 1's e2e (the captioned video case) still produces
  byte-identical output to PR #31's manual e2e (proof of no
  regression on the captions path)
- The yt-dlp `ydl_opts` dict in production code is byte-identical
  to the one in `requirements.md` `## Reference calls (verbatim)`
  (CLAUDE.md vendor-API guardrail — caught by the
  `test_ydl_opts_match_spec` test)
- PR body uses `Closes #21`
- Per-PR teaching artifacts shipped (the spec PR + impl PR
  explainers, journey, interview-prep STAR hook)
- Multi-vendor review pass complete (Codex + pr-review-toolkit;
  same convention as PR #31)

After merge: board card auto-moves to Done (workflow enabled in
PR #33), PR #21 auto-closes via `Closes #21`. PLAN.md flipped
(Slice 2 shipped; Slice 2b queued for faster-whisper).
