# Drive Upload Feature — Design Spec

**Date:** 2026-05-05
**Status:** approved — ready for implementation planning
**Scope:** CLI-only (Drive upload + standalone upload command + OAuth setup)
**Follow-up spec:** Angular + FastAPI local UI (separate brainstorm)

---

## Problem

Transcripts are written locally only. Users who work primarily in Google Drive
have to manually upload the `.md` output after every transcription run. There
is also no way to upload a previously-transcribed file to Drive without doing
a full re-transcription. Both gaps are addressed here.

---

## CLI surface

```bash
# One-time OAuth setup
ssm-transcriber auth google-drive

# Transcribe and upload in one step
ssm-transcriber transcribe "drive://FILE_ID" --upload-to-drive [--drive-folder FOLDER_ID]
ssm-transcriber transcribe ./video.mp4 --upload-to-drive [--drive-folder FOLDER_ID]

# Upload an already-transcribed file
ssm-transcriber upload ./output/Session20-transcript.md [--drive-folder FOLDER_ID]
```

**Finding a folder ID:** open the target folder in Google Drive; the URL is
`https://drive.google.com/drive/folders/<FOLDER_ID>`. Copy the last segment.
Same pattern as the `drive://FILE_ID` source URIs already in use.

---

## Architecture

### New files

```
src/transcriber/destinations/
    __init__.py
    base.py       # OutputDestination Protocol
    drive.py      # DriveDestination — wraps google-api-python-client
src/transcriber/core/auth.py   # OAuth token storage + refresh
```

### Modified files

| File | Change |
|------|--------|
| `cli.py` | `--upload-to-drive` + `--drive-folder` on `transcribe`; new `upload` subcommand; new `auth google-drive` subcommand |
| `config.py` | Add `TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID: str | None` setting |
| `pyproject.toml` | Add `google-api-python-client` + `google-auth-oauthlib` deps |
| `.env.example` | Add `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID` |

### `OutputDestination` Protocol

```python
# src/transcriber/destinations/base.py
from pathlib import Path
from typing import Protocol

class OutputDestination(Protocol):
    def upload(self, path: Path, filename: str) -> str:
        """Upload file to destination. Returns a URL or location string."""
        ...
```

One interface, one method. `DriveDestination` is the only concrete
implementation today. Adding S3, Notion, or any other destination later
is a new class + a new CLI flag — nothing else changes.

This mirrors the existing `TranscriptionProvider` pattern in the codebase.

### `DriveDestination`

```python
# src/transcriber/destinations/drive.py
class DriveDestination:
    def __init__(self, folder_id: str, token_path: Path): ...
    def upload(self, path: Path, filename: str) -> str:
        # calls files().create() via google-api-python-client
        # returns https://drive.google.com/file/d/<id>/view
        ...
```

### Auth (`core/auth.py`)

- Token stored at `~/.config/transcriber/google_token.json`
- OAuth scopes: `drive.file` (create/modify only files created by this app —
  minimal footprint, not full Drive read access)
- `google-auth-oauthlib` handles token refresh automatically
- `auth google-drive` subcommand: opens browser → consent → saves token
- If token is missing or refresh fails: raises an `AuthError` that the CLI
  maps to exit code 2 with a clear message

### OAuth credentials

User provides their own Google Cloud project credentials via `.env`:

```
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
```

Instructions for creating credentials (Cloud Console → APIs & Services →
Credentials → OAuth 2.0 Client ID → Desktop app) must be added to `README.md`
under a new **"Google Drive setup"** section. See documentation note below.

---

## Data flow

### `transcribe ... --upload-to-drive`

```
existing transcription flow runs
  └─ markdown written to local output path  ← always happens first
  └─ resolve_folder_id()                    ← --drive-folder > config > error
  └─ DriveDestination.upload(path, filename)
  └─ CLI prints: "Uploaded → https://drive.google.com/file/d/..."
```

### `upload <file>`

```
validate file exists on disk         ← exit 1 if not
resolve_folder_id()                  ← --drive-folder > config > error
DriveDestination.upload(path, filename)
CLI prints: "Uploaded → https://drive.google.com/file/d/..."
```

### Folder resolution (both flows)

1. `--drive-folder FOLDER_ID` flag → use it
2. `TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID` in config/env → use it
3. Neither set → exit 2: `"No Drive folder configured. Pass --drive-folder or set TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID"`

---

## Error catalogue

| Scenario | Exit code | Message |
|----------|-----------|---------|
| Never authenticated | 2 | `"Run ssm-transcriber auth google-drive first"` |
| Token expired / revoked | 2 | `"Drive token expired — rerun ssm-transcriber auth google-drive"` |
| Folder not found / no access | 2 | `"Drive folder not found or not accessible: {folder_id}"` |
| Upload fails (network/API) | 3 | `"Drive upload failed: {reason}. Transcript saved locally at {path}"` |
| Local file missing (`upload` cmd) | 1 | `"File not found: {path}"` |
| No folder configured | 2 | See folder resolution above |

**Key invariant:** the local `.md` file is written before any upload attempt.
Upload failure never causes transcript loss.

---

## Testing strategy

### Unit tests

**`tests/unit/test_drive_destination.py`**
- `DriveDestination.upload()` — mock `googleapiclient` at the class boundary
- Happy path: returns a Drive URL
- Folder not found: raises the correct error
- Network failure: error surfaced, does not delete local file

**`tests/unit/test_auth.py`**
- Token save / load round-trip
- Expired token → `AuthError`, not silent fallback

### CLI tests (extend `test_cli.py`)
- `--upload-to-drive` with no token → exit 2 + correct message
- `--upload-to-drive` with no folder configured → exit 2 + correct message
- `upload` with missing file → exit 1
- `upload` happy path → `DriveDestination.upload()` called with correct path

### Integration tests (`@pytest.mark.integration`, skipped unless `SSM_INTEGRATION=1`)
- Real Drive upload to a known test folder
- Verify returned URL is accessible

**Mock boundary:** unit tests mock at the `DriveDestination` level, not inline
`googleapiclient` calls, so the mock shape matches what the real class receives.

---

## Documentation note

**This feature requires two README updates before it can be used:**

1. **Google Drive setup section** — step-by-step instructions for:
   - Creating a Google Cloud project
   - Enabling the Drive API
   - Creating OAuth 2.0 credentials (Desktop app type)
   - Adding `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` to `.env`
   - Running `ssm-transcriber auth google-drive`

2. **Transcription quick-start section** — end-to-end usage examples showing
   the full workflow from install → transcribe → upload. This is a broader gap:
   `README.md` currently has phase checkboxes but no practical "here's how to
   actually use it" guide. This feature is a good forcing function to add one.

Both doc updates should land in the same PR as the implementation, not as a
follow-up.

---

## Out of scope (future specs)

- Angular + FastAPI local UI (separate spec — wraps this CLI)
- Drive Slice 3: OAuth for private Drive *source* files (separate spec)
- Multiple simultaneous upload destinations (e.g. Drive + S3 in one run)
- Upload formats other than `.md`
