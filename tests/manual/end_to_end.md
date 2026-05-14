# Manual end-to-end runbook — AssemblyAI MVP Slice 1

This runbook is the single real-API verification step for Slice 1. **It
costs money** (~$0.005 per run against the documented short-WAV fixture)
and stays out of CI on purpose.

## Prerequisites

- `ffmpeg` installed (`brew install ffmpeg` on macOS).
- An AssemblyAI account with at least a few cents of credit.
- A short WAV or audio/video file at ~10 seconds (to keep the bill negligible).

## Setup (one-time)

```bash
cp .env.example .env
# Edit .env and set:
#   ASSEMBLYAI_API_KEY=<your-actual-key>
uv sync --extra dev
```

## Steps

1. Pick a short audio source you can re-run cheaply. Tip: macOS's `say`
   command produces a small WAV in seconds:

   ```bash
   say -o sample.aiff "This is a short test clip for the SSM Transcriber MVP slice."
   ffmpeg -i sample.aiff -ar 16000 -ac 1 -c:a pcm_s16le sample.wav
   ```

2. Dry-run with the default budget — should refuse cleanly with exit 2:

   ```bash
   uv run ssm-transcriber transcribe sample.wav -y
   echo "exit: $?"
   ```

   **Expected**: error message naming AssemblyAI as paid + the
   `--budget low` (or `--budget best`) rerun hint, exit code `2`. No charge
   incurred.

3. Real run with `--budget low`:

   ```bash
   uv run ssm-transcriber transcribe sample.wav --budget low -y
   echo "exit: $?"
   ```

   **Expected**:
   - The estimated cost line prints (~$0.001-0.002 for a 10-second file).
   - `AssemblyAI job ID:` line prints once (recoverable identifier).
   - A polling spinner runs ~5-15 seconds for short audio.
   - `✓ Saved to: ./output/sample-YYYY-MM-DD.md`.
   - Exit code `0`.

4. Open the output file and verify:
   - YAML frontmatter present, with all expected fields populated:
     `title`, `source_uri` (`file:///...` absolute), `source_kind: local`,
     `duration_seconds`, `language`, `provider: assemblyai`,
     `model: universal-3-pro` (or whatever `--model` was passed),
     `diarized`, `speakers`, `assemblyai_job_id`, `created` (today).
   - `# {title}` H1 line.
   - Summary blockquote with duration / language / model.
   - `## Transcript` heading.
   - At least one line with the transcribed text.

5. Re-run the same command — verifies the suffix-increment collision
   policy:

   ```bash
   uv run ssm-transcriber transcribe sample.wav --budget low -y
   ```

   **Expected**: a second file appears as `sample-YYYY-MM-DD-2.md`. The
   previous file is intact.

6. Sanity-check the actual cost in the AssemblyAI dashboard. The total
   spend for steps 3 and 5 should be well under $0.01.

## Recording the result

Add a one-line entry to the PR's verification evidence with:

- Exit codes observed for steps 2 and 3.
- The two output filenames produced.
- The actual AssemblyAI cost shown in the dashboard.

If anything diverges from "Expected", do **not** mark Slice 1 done —
file a follow-up against the spec or the implementation.

---

# Manual end-to-end runbook — Drive Source URL Passthrough (Slice 2)

This is the single real-API verification step for Slice 2. **It costs
money** (~$0.005–0.60 depending on file length) and stays out of CI.
Unlike Slice 1, no local file is uploaded — AssemblyAI fetches the
public Drive URL directly.

## Prerequisites

- An AssemblyAI account with credit (same as Slice 1).
- A Drive video or audio file shared as **anyone-with-link can view**.
  The file must be one the user actually wants transcribed (per the
  paired-paid-verification convention) — not a synthetic test sample.

## Steps

1. Confirm the Drive sharing setting is "Anyone with the link" (not
   "Restricted"). In Drive: right-click → Share → "General access:
   Anyone with the link". This is the **only** auth model Slice 2
   supports; OAuth + private files lands in Slice 3.

2. Test the validation error path first (no real call, no charge):

   ```bash
   uv run ssm-transcriber transcribe "drive://" --budget low -y
   echo "exit: $?"
   ```

   **Expected**: error message containing "could not extract a Drive
   file ID", exit code `2`. No charge.

   *Note: don't use `drive://invalid-malformed` here — hyphens are valid
   characters in Drive file IDs (URL-safe base64), so that string parses
   successfully and the run reaches AssemblyAI before the URL fetch
   fails (exit 3, no transcription cost). Use `drive://` (empty)
   to verify the parser rejection path properly.*

3. Test the budget gate (default `--budget free` blocks Drive too):

   ```bash
   uv run ssm-transcriber transcribe "drive://1Zdp9aYV..." -y
   echo "exit: $?"
   ```

   **Expected**: exit code `2` with the "paid provider" Gate 2 message.
   No charge incurred.

4. Real run with `--budget low` and a `--title` you want to read later:

   ```bash
   uv run ssm-transcriber transcribe \
     "drive://<your-file-id>" \
     --title "<descriptive title with spaces>" \
     --budget low -y
   echo "exit: $?"
   ```

   The CLI accepts any of the five Drive URL forms documented in
   `specs/2026-05-04-drive-source-passthrough/requirements.md`
   §"Reference calls (verbatim)" — pick whichever form is convenient
   to copy from the browser.

   **Expected**:
   - The Drive notify message prints — must contain `per-minute` and
     `dashboard` (validation case 20). NO local cost estimate appears
     (we have no local duration to estimate against).
   - `AssemblyAI job ID:` line prints once.
   - A polling spinner runs (server-side fetch + transcription).
   - `✓ Saved to: ./output/{title-with-dashes}-YYYY-MM-DD.md`.
   - Exit code `0`.

5. Verify path-traversal protection and that nothing wrote outside
   `output_dir` (validation case 26a):

   ```bash
   ls -la $(dirname "$PWD")/  # parent dir — should NOT contain any new files
   ```

   The `--title` with `..` or `/` in earlier test would have failed at
   exit 2; this `ls` confirms no errant file landed via collision suffix
   resolution either.

6. Open the output file and verify:
   - YAML frontmatter `title:` matches the user's `--title` (whitespace
     preserved in the frontmatter, replaced with `-` only in the
     filename — validation case 26b).
   - `source_uri: drive://<file-id>` — the canonical form, NOT the full
     URL the user pasted (validation case 25's central round-trip
     assertion).
   - `source_kind: google_drive`.
   - **No `file://` URL anywhere in the output** (validation case 27).
   - `duration_seconds:` populated by AssemblyAI (we didn't probe
     locally; this comes from the server response).
   - `provider: assemblyai`, `assemblyai_job_id` populated.
   - `# {title}` H1 line, `## Transcript` heading, transcribed lines.

7. Sanity-check the actual cost in the AssemblyAI dashboard. The bill
   should match the per-minute math (file duration × $0.009/min).
   Capture the actual cost in the PR explainer per the
   "cost-vs-estimate gap" learning the plan calls out.

## Recording the result

Add to the PR's verification evidence:

- Exit codes observed for steps 2, 3, 4.
- The output filename produced (full path).
- The actual AssemblyAI cost shown in the dashboard for step 4.
- Whether step 5's `ls` showed any new files in the parent dir
  (must be **no**).

If anything diverges from "Expected", do **not** mark Slice 2 done.

---

# Manual end-to-end runbook — YouTube Captions Passthrough (Phase 2 Slice 1)

This is the single real-API verification step for Phase 2 Slice 1
(issue #20). **It costs $0** — the captions path skips AssemblyAI
entirely and uses `youtube-transcript-api` (free, unofficial scraper)
plus one fail-soft GET to YouTube's public oembed endpoint for the
title. The only "real-API" verification is "does this work against a
real public YouTube video the captions API actually responds to."

## Prerequisites

- A public YouTube video the user knows has captions (manual or
  auto-generated). Pick a short video to keep the test cheap — `say`
  + `ffmpeg` can produce a fixture, but for captions verification a
  real YouTube URL the user has watched works better.
- A second public YouTube URL the user knows does NOT have captions
  (creator disabled them, or no auto-generated track). This verifies
  the no-captions error wording in real CLI output.

## Steps

1. Test URL parsing rejection paths first (no network call):

   ```bash
   uv run ssm-transcriber transcribe "https://www.youtube.com/playlist?list=PL123"
   echo "exit: $?"
   ```

   **Expected**: exit code `2`, message containing "supply a single
   video URL". No network call fired.

2. Real run against a captioned video:

   ```bash
   uv run ssm-transcriber transcribe "https://youtu.be/<CAPTIONED_ID>"
   echo "exit: $?"
   ```

   **Expected**:
   - INFO log line: `YouTube captions source: video=<ID>
     lang=<en|hi|...> caption_type=<manual|auto>`.
   - `✓ Saved to: ./output/<oembed-title-or-video-id>-YYYY-MM-DD.md`.
   - Exit code `0`.
   - **No** budget gate prompt, **no** AssemblyAI job ID line, **no**
     polling spinner — the captions path skips all three.

3. Open the output file and verify:
   - YAML frontmatter `source_kind: youtube_captions`.
   - `source_uri: https://youtu.be/<VIDEO_ID>` (canonical short form,
     NOT the full watch URL).
   - `provider: youtube-captions`.
   - `model: null`.
   - `caption_type: manual` (or `auto`).
   - `diarized: false`, `speakers: null`, `assemblyai_job_id: null`.
   - `duration_seconds` populated (end of last caption segment).
   - `language: <ISO code>` matching the caption track YouTube
     returned.
   - Body summary contains `youtube-captions (manual)` or
     `youtube-captions (auto)`, **not** `assemblyai/<anything>`.
   - Transcript lines have `[mm:ss]` timestamps but **no**
     `**Speaker A:**` prefixes (captions have no speakers).

4. Real run against a captionless video:

   ```bash
   uv run ssm-transcriber transcribe "https://youtu.be/<NO_CAPTION_ID>"
   echo "exit: $?"
   ```

   **Expected**: exit code `2`, error output contains:
   - "Video has no usable captions" (literal phrase).
   - `https://github.com/manjunath84/SSM-Transcriber/issues/21` (the
     Slice 2 pointer).
   - The copy-paste `uv run yt-dlp -x --audio-format wav ...` +
     `uv run ssm-transcriber transcribe /tmp/audio.wav` workaround.

5. `--title` override sanity check:

   ```bash
   uv run ssm-transcriber transcribe \
     "https://youtu.be/<CAPTIONED_ID>" \
     --title "My Custom Title"
   ```

   **Expected**: output filename uses `My-Custom-Title-YYYY-MM-DD.md`
   (whitespace → dash in filename, preserved in YAML frontmatter
   `title: "My Custom Title"`).

6. `--budget free` sanity check (validation #50):

   ```bash
   uv run ssm-transcriber transcribe "https://youtu.be/<CAPTIONED_ID>" --budget free
   echo "exit: $?"
   ```

   **Expected**: exit code `0`. Captions path bypasses the budget
   gate entirely — `--budget free` is allowed because the path is $0
   by construction. The Drive variant of this command would exit 2;
   the captions variant should succeed.

## Recording the result

Add to the PR's verification evidence:

- Exit codes observed for steps 1, 2, 4, 5, 6.
- The output filename produced for step 2.
- The exact error output for step 4 (verifies the no-captions
  message wording).
- Whether oembed returned a title for step 2 (compare the filename
  against the video ID stem — if they differ, oembed worked; if
  the filename is the bare video ID, oembed failed soft).

If anything diverges from "Expected", do **not** mark Phase 2
Slice 1 done.

---

## Phase 2 Slice 2 — yt-dlp audio fallback (captionless videos)

These tests exercise the audio-fallback path Slice 2 adds. They
require a captionless YouTube URL — YouTube Shorts are the most
common captionless content type, but verify before running by
opening the URL in a browser and confirming the captions button
shows "No captions available" (or equivalent). Save the chosen URL
as `<NO_CAPTION_ID>` for the steps below.

Set `ASSEMBLYAI_API_KEY` for steps that use `--budget low`. The
captioned-video regression check at the top of this doc must still
produce byte-identical output to PR #31's run.

1. Captionless video on `--budget free` — short-circuit, no
   download attempted:

   ```bash
   uv run ssm-transcriber transcribe "https://youtu.be/<NO_CAPTION_ID>"
   echo "exit: $?"
   ```

   **Expected**: exit `2` with a message that names the video,
   says captions are unavailable, and points the user at
   `--budget low`. No yt-dlp probe or download should occur. Total
   wall time should be a few seconds (just the captions library
   round-trip).

2. Captionless video on `--budget low` + decline — probe runs,
   prompt fires, user types `n`, no download:

   ```bash
   uv run ssm-transcriber transcribe "https://youtu.be/<NO_CAPTION_ID>" --budget low
   # When prompted "Estimated cost ~$X.XX — proceed?", type "n".
   echo "exit: $?"
   ```

   **Expected**: exit `0`. The cost prompt shows a real dollar
   estimate based on the probed duration (NOT `$0.00`). The output
   includes `Cancelled by user; no charge incurred.` No `output/*.md`
   is produced.

3. Captionless video on `--budget low -y` — full audio-fallback
   happy path:

   ```bash
   uv run ssm-transcriber transcribe "https://youtu.be/<NO_CAPTION_ID>" --budget low -y
   echo "exit: $?"
   ```

   **Expected**: exit `0`, with an `output/<title>-YYYY-MM-DD.md`
   file. Frontmatter must show:

   ```yaml
   source_kind: youtube_audio
   source_uri: https://youtu.be/<NO_CAPTION_ID>   # canonical short form
   provider: assemblyai
   model: universal-3-pro                           # or whatever AAI default
   assemblyai_job_id: <real job id>                 # NOT null
   # NO caption_type field for this kind
   ```

   No `file://` URI should appear in the frontmatter. Body summary
   reads `assemblyai/universal-3-pro` (NOT `youtube-captions
   (...)`). The workspace audio file should be cleaned up after
   the run (no leftover `audio.*` files outside the workspace).

4. Captioned video regression — Slice 1 path still wins:

   Re-run step 2 from the Phase 2 Slice 1 section above with the
   captioned URL you used for PR #31's verification. Expected
   output must be byte-identical to that earlier run except for
   the date in the filename and frontmatter. The audio-fallback
   path must NOT fire when captions exist.

5. (Optional) Invalid / private video on `--budget low` —
   exit-code matrix sanity:

   ```bash
   uv run ssm-transcriber transcribe "https://youtu.be/00000000000" --budget low
   echo "exit: $?"
   ```

   **Expected**: exit `2`. The `00000000000` video doesn't exist
   so the captions library raises `VideoUnavailable` *before*
   `NoCaptionsAvailable` is ever produced. This validates that
   "video doesn't exist" is NOT silently routed into the audio
   fallback (which couldn't help either).

### Recording Slice 2 results

Add to the PR's verification evidence:

- The captionless `<NO_CAPTION_ID>` you chose and a one-line
  confirmation that it actually had no captions.
- Exit codes observed for each of steps 1–5.
- The output filename produced for step 3.
- A 5–10-line excerpt of the step 3 frontmatter showing
  `source_kind: youtube_audio` and a populated `assemblyai_job_id`.
- The cost-estimate dollar amount shown in step 2 (and 3 if the
  prompt is rendered above the `-y` skip — depends on terminal
  width). Verifies the probe-derived duration was used.

If anything diverges, do **not** mark Phase 2 Slice 2 done.
