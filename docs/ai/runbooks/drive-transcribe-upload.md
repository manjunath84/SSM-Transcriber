# Drive Transcribe + Upload Runbook

End-to-end manual steps to transcribe a Google Drive video/audio file and
upload the markdown transcript to a Drive folder.

## What this does

`uv run ssm-transcriber transcribe drive://FILE_ID --upload-to-drive --drive-folder FOLDER_ID`
runs three things in order:

1. **Source resolution** — AssemblyAI fetches the file directly from
   Google's CDN (URL passthrough; no local download, no `ffmpeg`).
2. **Transcription** — paid AssemblyAI call (`--budget low` minimum).
3. **Upload** — the rendered `.md` is written locally first, then
   uploaded to your Drive folder. The local copy is **always** written
   before upload is attempted, so a failed upload never costs the
   transcript.

If you only want to push an existing `.md`, use the standalone
`upload <file>` subcommand instead — no AssemblyAI call.

## Prerequisites

- `ASSEMBLYAI_API_KEY` set in `.env` (paid).
- `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` set in `.env`
  (set up below; one-time).
- The source Drive file is **shared as "Anyone with the link"** —
  AssemblyAI's servers fetch it directly, so they can't authenticate
  as you. If the file is private, the run fails at provider step
  (exit 3).
- The destination Drive folder is owned by you (or you have edit
  access). The `drive.file` scope means the app can only see/touch
  files it creates, so you do **not** share the folder with the app.

## Step 1 — Google OAuth credentials (one-time, ~5 min, free)

1. Open https://console.cloud.google.com/apis/credentials and select or
   create a project.
2. **APIs & Services → Library** → search **Google Drive API** →
   **Enable**.
3. **APIs & Services → OAuth consent screen**:
   - User type: **External**.
   - Fill app name (e.g. `ssm-transcriber`), support email, developer
     contact email.
   - Add scope `.../auth/drive.file` (only files the app creates).
   - Under **Test users** add the Google account that will run the CLI.
4. **APIs & Services → Credentials → Create Credentials → OAuth client
   ID**:
   - Application type: **Desktop app**.
   - Name: `ssm-transcriber` (or anything).
   - Click **Create** — copy the **Client ID** and **Client secret**
     from the dialog.
5. Paste both into `.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=<paste>
   GOOGLE_OAUTH_CLIENT_SECRET=<paste>
   ```
   Optional: set a default folder so you don't need `--drive-folder`
   on every run:
   ```
   TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID=<folder-id>
   ```
   (Folder ID is the last segment of the folder's URL.)

## Step 2 — Confirm source file is shareable

URL passthrough means AssemblyAI fetches the file directly. Open the
source URL in an **incognito window** (logged out):

- If the file previews without a sign-in prompt → sharing is correct.
- If you get "Sign in to view" or "Access denied" → in your normal
  browser, right-click the file → **Share** → change "Restricted" to
  **"Anyone with the link" → Viewer** → Done.

## Step 3 — Run the OAuth consent flow (one-time, free)

```bash
uv run ssm-transcriber auth google-drive
```

A browser tab opens. Sign in, click **Allow** on the consent screen
("ssm-transcriber would like to view and manage Google Drive files
that you have opened or created with this app").

Success output: `Google Drive authenticated. Token saved.`

The refresh token is persisted to
`~/.config/transcriber/google_token.json` with mode `0600`. Subsequent
runs auto-refresh the access token; no further consent is needed
unless you revoke access in your Google Account settings.

## Step 4 — Transcribe and upload

```bash
uv run ssm-transcriber transcribe \
  drive://FILE_ID \
  --upload-to-drive \
  --drive-folder FOLDER_ID \
  --budget low
```

`FILE_ID` is the segment between `/d/` and `/view` in the source URL.
`FOLDER_ID` is the last segment of the destination folder URL.

Optional flags:

| Flag | Effect |
|------|--------|
| `--title "My session"` | Renames the `.md` file and YAML frontmatter title (default: file ID). |
| `-y` | Skip the cost-confirmation prompt. |
| `--max-wait 60` | Raise polling cap if the file is long (default 30 min). |
| `--no-speakers` | Skip diarization (cheaper, faster). |

Expected sequence:

1. Budget gate prompt:
   *"Provider: AssemblyAI · URL passthrough — AssemblyAI bills
   per-minute against the public URL; exact cost in the AssemblyAI
   dashboard after the run."* → press `y`.
2. `[cyan]AssemblyAI job ID:[/cyan] <id>` (useful for the dashboard).
3. Polling until done. No `ffmpeg` is invoked (Drive passthrough).
4. `[green]✓[/green] Saved to: output/<stem>-<date>.md`.
5. `Uploaded → https://drive.google.com/file/d/<new-id>/view`.
6. Exit 0.

## Failure modes

The headline guarantee is **transcript-loss-impossible**: the local
`.md` is always written before any upload. Pre-flight failures
(folder, auth) exit before the paid call; post-extract failures keep
the `.md` on disk so a manual retry is one command away.

| Symptom | Exit | Meaning | Recovery |
|---------|------|---------|----------|
| `Google OAuth credentials not configured.` | 2 | Step 1 not done | Add `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` to `.env`. |
| `Not authenticated with Google Drive...` | 2 | No token yet (or revoked) | Re-run `auth google-drive`. |
| `No Drive folder configured.` | 2 | Folder ID didn't reach the CLI | Re-check `--drive-folder` arg. |
| Provider 403 / "could not download source" | 3 | Source not shareable | Re-do Step 2. |
| Polling exceeds `--max-wait` | 3 | File longer than the cap | Re-run with `--max-wait 60` (or higher). |
| `error: <msg>` then `[yellow]Transcript saved locally at <path>[/yellow]` | 4 | Auth/network failure **after** transcription; `.md` is on disk | `uv run ssm-transcriber upload <path> --drive-folder FOLDER_ID` (no AssemblyAI re-charge). |
| `Drive upload failed: <reason>. Transcript saved locally at <path>` | 4 | Drive API error after transcription | Same as above. |

Exit codes follow the project matrix `{0, 2, 3, 4}`:

- **2** = config to fix (auth missing, folder unset, OAuth credentials
  unset). No paid work happened.
- **3** = upstream provider failure (AssemblyAI 4xx/5xx, source
  unreachable, polling timeout).
- **4** = local resource problem with recovery possible (file not
  found on `upload`; Drive upload failed but transcript is on disk).
- **0** = success or user-cancelled at the budget gate.

## Notes

- The `drive.file` scope is intentional and minimal: the app can only
  see files it creates. It cannot list, read, or modify any other
  files in your Drive.
- The token file is created with `O_CREAT|O_WRONLY|O_EXCL, 0o600` so
  it is never world/group-readable, even transiently. The atomic
  rename keeps the directory consistent across crashes.
- Refresh-token failures (token revoked, refresh server error) raise
  `AuthError` with a "Rerun: ssm-transcriber auth google-drive" hint.
- `transcribe` runs an auth pre-flight before any AssemblyAI call. A
  user without a token learns immediately, not after paying.
