# PR #19 — Drive Upload: transcript → Google Drive

**Merged:** TBD  |  **Branch:** `feat/drive-upload`  |  **Codex review:** TBD
**Journey entry:** [`../journey.md#pr-19--drive-upload`](../journey.md)

## The problem in one paragraph

After transcription, the `.md` output lived only on the local machine. Users
who work in Google Drive had to manually upload every file. There was also no
way to upload a previously-transcribed file without re-running the full
pipeline. This PR adds `--upload-to-drive` to `transcribe` and a standalone
`upload` subcommand, both backed by a thin `OutputDestination` protocol that
makes adding future destinations (S3, Notion) a one-class change.

## What changed (high level)

- `core/auth.py` — OAuth token storage and refresh; `AuthError` → exit 2; token persisted with 0600 permissions
- `destinations/base.py` — `OutputDestination` Protocol + `DestinationError`
- `destinations/drive.py` — `DriveDestination.upload()` wrapping `google-api-python-client`
- `cli.py` — `auth google-drive` subcommand; `upload` subcommand; `--upload-to-drive` + `--drive-folder` flags on `transcribe`; `_resolve_drive_folder()` shared helper; fail-fast folder + auth credential check before any transcription work
- `config.py` — `TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID` setting; `google_oauth_client_id`, `google_oauth_client_secret`, `google_oauth_configured` properties (follow the `assemblyai_configured` pattern — third-party keys read via `os.getenv` inside config properties)
- `README.md` — Google Drive setup guide + transcription quick-start

## Why this approach

`OutputDestination` is a 3-line Protocol — the same structural-typing
pattern as `TranscriptionProvider`. The cost is near zero; the benefit
is that a second destination (S3, Notion) is a new class and a new CLI
flag, with no changes to the upload orchestration logic. Reviewed against
YAGNI: one protocol, one concrete implementation, no registry.

Auth is a prerequisite command (`auth google-drive`) rather than an inline
browser popup during transcription, keeping the auth concern separate from
the run flow — same principle as the two-gate spend model.

The local `.md` is always written before upload is attempted and the fail-fast
folder check fires before any transcription work — both are architectural
invariants, not just conventions.

## New Python idioms introduced

- `typing.Protocol` — structural subtyping ("duck typing with a contract"). See [`python-notes.md → typing.Protocol`](../python-notes.md) for the existing Protocol entry.

## What a reviewer should notice

- The local `.md` is always written before upload is attempted — transcript loss on upload failure is impossible by construction.
- `drive.file` OAuth scope (not `drive`) — the app can only see files it created, not the user's full Drive.
- Exit codes split by recoverability, not just error type: `AuthError` (config to fix) → exit 2; `DestinationError` (file/transcript on disk, retry possible) → exit 4. After a paid `transcribe` run, both map to exit 4 because the .md is on disk regardless of which one fired.
- `_resolve_drive_folder` is shared between `transcribe` and `upload` — folder resolution logic lives in one place.
- Token file is written atomically with secure mode from byte zero: `os.open(..., O_CREAT|O_WRONLY|O_EXCL, 0o600)` ensures the file is never world/group-readable even transiently. The trailing `tmp.replace()` is inside the `try` so a failed rename cleans up the token-bearing `.tmp` rather than leaking it.
- `--upload-to-drive` fails fast on both folder config and Drive credentials before any audio extraction or paid API call — a user without a token learns immediately, not after paying AssemblyAI.
- The plan's initial test specifications used exit 1 for configuration errors, which is outside the project's `{0, 2, 3, 4}` matrix. Exit 1 was corrected to exit 2 (config error) for unknown-provider and exit 4 (local file not found) for missing-file cases, consistent with how `transcribe` handles `FileNotFoundError`.

## Interview angle

- **Story type:** extensible design at low cost — Protocol pattern applied to a new output destination, consistent with existing provider pattern.
- **One-sentence hook:** "Added Drive upload by defining a 3-line OutputDestination Protocol first, so the implementation is a single concrete class with no special-casing in the CLI orchestration."
- **Code review findings caught:** token file permissions (fixed via atomic write — no world-readable window), webViewLink escape, test hermiticity (output_dir not isolated), exit-code matrix violations, `build()` outside try block, `authenticate_drive()` unguarded, `TransportError` uncaught, `os.getenv` in CLI violating config-singleton rule, auth fail-fast missing before paid call — all caught and fixed during the PR review cycle.
- **Pointer:** [`interview-prep.md`](../interview-prep.md) — relates to the PreparedMedia DTO boundary design story.

## Further reading

- [`docs/superpowers/specs/2026-05-05-drive-upload-design.md`](../../superpowers/specs/2026-05-05-drive-upload-design.md) — the approved design spec.
- [`pr-003-phase-1-foundations.md`](pr-003-phase-1-foundations.md) — `typing.Protocol` and the Provider pattern this mirrors.
