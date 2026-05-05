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
