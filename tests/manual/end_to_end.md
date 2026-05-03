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
