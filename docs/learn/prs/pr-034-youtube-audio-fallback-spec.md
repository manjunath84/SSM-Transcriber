# PR #34 — Spec: YouTube Source (yt-dlp Audio Fallback)

**Merged:** 2026-05-13  |  **Branch:** `feature/youtube-audio-fallback-spec`
**Journey entry:** [`../journey.md#pr-34--spec-youtube-source-yt-dlp-audio-fallback`](../journey.md#pr-34--spec-youtube-source-yt-dlp-audio-fallback)

## The problem in one paragraph

PR #30 / #31 (Phase 2 Slice 1) shipped the captions-only YouTube
source — `$0` for videos that have manual or auto-generated captions.
The slice exited 2 with a "use yt-dlp manually" workaround for
captionless videos. This PR is the spec PR that designs the actual
audio fallback: when captions are missing or disabled, run `yt-dlp`
to download audio and route it through the existing local-file
pipeline → AssemblyAI. The impl PR (#35) lands the code.

## The scope audit that almost wasn't

`docs/PLAN.md` originally bundled Slice 2 as "yt-dlp + faster-whisper
local ASR" — captionless videos would run through the local provider
for `$0` instead of paying AssemblyAI. The brainstorm started from
that scope and immediately ran into a problem: the codebase has
`transcription_provider: "faster_whisper"` declared in `config.py`
defaults but **no `providers/faster_whisper.py` exists**. Slice 1's
verification of "Phase 0–1 + Phase 4 shipped" silently included
faster-whisper as a planned-not-shipped provider.

Bundling a new source + new provider + new budget router in one
slice would dilute all three. Spec PR opens with a three-option
scope split:

- (A) Slice 2 = yt-dlp + AssemblyAI; faster-whisper deferred
- (B) Slice 2 = all three (largest scope)
- (C) Two slices: 2a yt-dlp + AAI, 2b faster-whisper

The user picks (A). The spec then carves the deferred faster-whisper
work into a new "Slice 2b" entry in PLAN.md so it doesn't get lost.
Caught before any code was written — exactly when scope audits are
cheapest.

## The seven design decisions

The brainstorm walked through seven design questions one at a time,
each settled before the next:

1. **One class owns both paths.** Three discrete methods (`prepare`,
   `probe_audio`, `download_audio`) the CLI orchestrates between.
   Source class stays money-agnostic — the budget gate lives in the
   CLI, same as `LocalSource` / `DriveSource`.

2. **Conservative fallback triggers.** Exactly two captions-library
   exceptions flow into audio: `TranscriptsDisabled` (creator turned
   captions off) and `NoTranscriptFound` (no track in any language).
   `VideoUnavailable`, `AgeRestricted`, `PoTokenRequired`,
   `InvalidVideoId`, the network family — all preserve Slice 1's
   exit codes and messages 1:1.

3. **Probe-first cost UX.** `yt-dlp.extract_info(download=False)` is
   a metadata-only round-trip returning `duration` + `title`. The
   budget gate fires *before* download with a real cost estimate.
   On `--budget free`, the path short-circuits before even probing
   (no network at all beyond the captions library call). Free budget
   + captionless = exit 2 with a budget-aware message.

4. **`youtube_audio` source-kind label.** Symmetric pair with Slice
   1's `youtube_captions`. The bare `"youtube"` literal was dead in
   Slice 1's `SourceKind` and is removed.

5. **`bestaudio/best` format, no postprocessors.** yt-dlp picks the
   cheapest audio stream YouTube serves (typically m4a or opus);
   the existing `extract_audio` normalises to 16 kHz mono WAV. One
   ffmpeg run, not two.

6. **yt-dlp's built-in retries.** `retries=3`, `fragment_retries=3`,
   `socket_timeout=30` on the `YoutubeDL` instance. yt-dlp's retry
   machinery is protocol-aware (HLS fragments, chunked-encoding
   resumes); wrapping it with tenacity would just double-retry.

7. **Exit-code matrix mirrors Slice 1.** `ExtractorError` family →
   2, `DownloadError` (network exhaustion) → 3,
   `PostProcessingError`/`OSError` → 4. New `ProbeDurationUnknown`
   exception (live streams / premieres return `duration=None`) maps
   to 2 with a "couldn't determine duration" message — protects
   against showing the user a fake `$0.00` cost prompt.

## Vendor API guardrail in action

CLAUDE.md is explicit: vendor API calls must be byte-for-byte
verbatim from a ctx7 fetch performed within the current PR. The
spec includes a `## Reference calls (verbatim)` section with the
`YoutubeDL` constructor options, `extract_info(download=False)`
return shape, and the `DownloadError`/`ExtractorError` exception
hierarchy fetched 2026-05-13 from `/yt-dlp/yt-dlp` via Context7.
A planned `test_ydl_opts_match_spec` test in the impl PR will
byte-compare the production `_YDL_OPTS_BASE` dict against this
reference — PR #12's lesson applied prospectively.

## Two review rounds, four reviewers, ten findings

The spec went through two external reviews before merge:

**Codex review** flagged four P2 findings, all real and all fixed:

- The `PreparedMedia` constructor example in plan.md omitted required
  `duration_seconds` + `workspace` fields and stored `probe_duration`
  as int (the dataclass uses `dict[str, str]` for `extra`). The
  impl PR would have failed at construction time.
- Double-budget-prompt regression: the new pre-download `budget_check`
  + the existing local-file pipeline's `budget_check` would fire
  twice. Spec gains a new §4e specifying a kind-aware bypass plus
  a regression test that counts prompt invocations.
- The probe reference call was missing `noplaylist=True`, contradicting
  the plan's `_YDL_OPTS_BASE`. The byte-for-byte test would have
  failed.
- `Architecture #1` still described the old two-method shape from
  a pre-revision draft; the rest of the spec already committed to
  three methods.

**pr-review-toolkit (comment-analyzer + code-reviewer)** flagged
five Important findings + suggestions:

- Three `§5c` references rotted to `§4c` during renumbering.
- Exit gate said "8 design decisions" but the architecture section
  only lists 7. Off-by-one.
- Brittle `cli.py:489-545` line range; switched to symbol-based anchor.
- `extra["probe_duration"]` stringification wasn't asserted in any
  test row.
- `ProbeDurationUnknown` was described in plan.md prose but missing
  from the validation matrix.

Plus a self-caught `§9 → §8` reference (the exit-gate referenced
itself).

## What this teaches

Two takeaways worth keeping:

**Scope audits at brainstorm time are nearly free.** Catching the
faster-whisper drift before code was written cost one extra
brainstorm question. Catching it after the impl PR was opened would
have cost a partial impl + a re-spec + a re-review. The discipline
is "check what's actually shipped vs. what the spec assumes" *before*
question 1.

**Spec reviews catch contract-level bugs the impl reviewer can't.**
Three of the four Codex findings were impossible to spot during
impl review — they'd have surfaced as test failures or runtime
errors. Reviewing the spec separately is the cheap test for the
spec's correctness; the impl review then only has to verify the
spec was followed, not whether the spec was self-consistent.
