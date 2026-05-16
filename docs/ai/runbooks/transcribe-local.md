# Guided Local-File Transcribe Runbook

AI-agnostic guide. Any tool (Claude Code, Codex CLI/UI, Cursor, VS Code
Copilot, Gemini CLI) follows this to walk a user through transcribing a
**local audio/video file** without the user recalling CLI flags.

## What this does

Drives `uv run ssm-transcriber transcribe <LOCAL_FILE> [options]` for a
file already on disk (`LocalSource` → audio extract → AssemblyAI →
markdown). The assistant asks the questions below in plain language,
assembles the command, shows it, and runs it only after the user
confirms.

## Cost reality (state this to the user before running)

Local-file transcription today is a **paid AssemblyAI call** and
requires `--budget low` (or `best`). `--budget free` is rejected for
local files because the $0 local provider (faster-whisper) is not yet
shipped (PLAN.md Phase 1 / Phase 2 Slice 2b, pending). Do not promise a
free local transcription. AssemblyAI bills per audio minute; the CLI
shows an estimate and prompts for confirmation before the paid call
unless `-y` is passed.

## Prerequisites (check, don't assume)

- `ASSEMBLYAI_API_KEY` set in `.env`. If missing, stop and tell the
  user to add it — the run will fail Gate 1 otherwise.
- The file exists and is a readable audio/video file. Resolve the path
  before building the command.
- For optional Drive upload only: `GOOGLE_OAUTH_CLIENT_ID` /
  `GOOGLE_OAUTH_CLIENT_SECRET` set and `auth google-drive` already run
  (see `drive-transcribe-upload.md`). Skip this whole branch if the
  user doesn't want Drive upload.

## Questions to ask the user (one at a time, in order)

1. **Which file?** Absolute or repo-relative path. Verify it exists
   before continuing.
2. **Multiple speakers?** Yes → diarization stays on (default). No /
   single speaker → add `--no-speakers` (cheaper, faster).
3. **Keep `mm:ss` timestamps in the transcript?** Yes → default. No →
   add `--no-timestamps`.
4. **Language?** "Auto-detect" → omit `-l`. Otherwise take a code like
   `en` → add `-l en`.
5. **Speech model?** Default `universal-3-pro` (most accurate). If the
   user wants the cheaper/older model → add `--model universal-2`.
6. **Custom output path?** Default writes
   `output/<file-stem>-<YYYY-MM-DD>.md`. If the user wants a specific
   path → add `-o <path>`.
7. **Also upload the transcript to Google Drive?** No → skip. Yes →
   confirm `auth google-drive` is done, then add `--upload-to-drive`
   and `--drive-folder <FOLDER_ID>` (or rely on
   `TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID`).

## Assemble and confirm

Build the command from the answers. `--budget low` is always included
for a local file (see Cost reality). Example shape:

```bash
uv run ssm-transcriber transcribe \
  "/path/to/recording.m4a" \
  --budget low \
  --no-speakers \
  -l en
```

Show the assembled command to the user verbatim and state the expected
cost framing ("AssemblyAI bills per audio minute; you'll be prompted to
confirm the estimate before any charge"). Run it only after the user
says go. Do **not** add `-y` unless the user explicitly asks to skip
the cost prompt.

## Expected sequence

1. Cost-confirmation prompt with an estimated `$` figure → user
   confirms.
2. `AssemblyAI job ID: <id>` line.
3. Polling until done (raise `--max-wait 60` if the file is long and
   polling times out at the 30-min default).
4. `✓ Saved to: output/<stem>-<date>.md`.
5. If `--upload-to-drive`: `Uploaded → https://drive.google.com/...`.
6. Exit 0.

## Failure modes

| Symptom | Exit | Meaning | Recovery |
|---------|------|---------|----------|
| Budget/auth error mentioning `free` not allowed | 2 | `--budget free` used for a paid local run | Re-run with `--budget low`. |
| `ASSEMBLYAI_API_KEY` missing message | 2 | Gate 1 not configured | Add the key to `.env`. |
| File not found | 4 | Bad path | Re-resolve the file path with the user. |
| Polling exceeds `--max-wait` | 3 | File longer than the cap | Re-run with `--max-wait 60` (or higher). |
| Upload error after `✓ Saved to:` | 4 | Drive failed; transcript is on disk | `uv run ssm-transcriber upload <path> --drive-folder <FOLDER_ID>` (no AssemblyAI re-charge). |

Exit codes follow the project matrix `{0, 2, 3, 4}` (see
`drive-transcribe-upload.md` for the canonical description).

## Notes

- This runbook never invents flags. Every flag here exists in
  `uv run ssm-transcriber transcribe --help`. If the CLI changes, update
  this runbook in the same PR.
- The $0 local path (faster-whisper) is future work; when PLAN.md
  Phase 1 / Slice 2b lands, revise the Cost reality section to offer
  `--budget free` for local files.
