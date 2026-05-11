# Drive Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Google Drive upload for transcripts — via `--upload-to-drive` on `transcribe` and a standalone `upload` subcommand — plus a one-time `auth google-drive` OAuth setup command.

**Architecture:** A thin `OutputDestination` Protocol (`destinations/base.py`) with `DriveDestination` as the only concrete implementation. An `auth` module (`core/auth.py`) owns OAuth token storage and refresh. The CLI resolves the Drive folder from `--drive-folder` flag → `TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID` env/config → error.

**Tech Stack:** `google-api-python-client`, `google-auth-oauthlib`, `typer`, `pydantic-settings`, `pytest` + `unittest.mock`

---

## Branch setup (do this before any task)

```bash
git checkout main
git pull
git checkout -b feat/drive-upload
```

---

## File map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/transcriber/core/auth.py` | OAuth token load/save/refresh, `AuthError` |
| Create | `src/transcriber/destinations/__init__.py` | Package init |
| Create | `src/transcriber/destinations/base.py` | `OutputDestination` Protocol, `DestinationError` |
| Create | `src/transcriber/destinations/drive.py` | `DriveDestination.upload()` |
| Create | `tests/unit/test_auth.py` | Auth module unit tests |
| Create | `tests/unit/test_drive_destination.py` | DriveDestination unit tests |
| Modify | `pyproject.toml` | Add google deps |
| Modify | `src/transcriber/config.py` | Add `drive_output_folder_id`, `google_oauth_configured` |
| Modify | `.env.example` | Add `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID` |
| Modify | `src/transcriber/cli.py` | Add `auth`, `upload` commands; add `--upload-to-drive` + `--drive-folder` to `transcribe` |
| Modify | `tests/unit/test_cli.py` | Add auth, upload, and transcribe-with-upload tests |
| Modify | `README.md` | Google Drive setup section + transcription quick-start |
| Modify | `docs/learn/journey.md` | PR entry |
| Modify | `docs/learn/prs/README.md` | PR row |
| Create | `docs/learn/prs/pr-019-drive-upload.md` | PR explainer (draft before opening PR) |

---

## Task 1: Add dependencies and config settings

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/transcriber/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add Google deps to pyproject.toml**

In `pyproject.toml`, add two lines inside `dependencies = [...]` after `"tenacity>=8.2.0"`:

```toml
    "google-api-python-client>=2.130.0",
    "google-auth-oauthlib>=1.2.0",
```

- [ ] **Step 2: Add Drive config fields to config.py**

In `src/transcriber/config.py`, add the new section after the `# ── LLM` section and before `# ── Logging`:

```python
    # ── Google Drive (upload destination) ────────────────────────────────────
    drive_output_folder_id: str | None = None
```

Then add a new property after `assemblyai_configured`:

```python
    @property
    def google_oauth_configured(self) -> bool:
        """Whether GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET are set.

        Per CLAUDE.md conventions, OAuth credentials are third-party keys
        so they are read unprefixed from os.environ rather than via
        pydantic-settings' TRANSCRIBER_ prefix.
        """
        return (
            bool((os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip())
            and bool((os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip())
        )
```

Also add `drive_output_folder_id` to the `redacted_dump` allowlist (it's a folder ID, not a secret). Find the allowlist dict and add:

```python
            "drive_output_folder_id",
```

- [ ] **Step 3: Update .env.example**

Add at the end of `.env.example`:

```bash
# ── Google Drive upload (optional) ──────────────────────────────────────────
# Create OAuth 2.0 credentials at: console.cloud.google.com → APIs & Services
# → Credentials → Create Credentials → OAuth client ID → Desktop app
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
# Drive folder to upload transcripts into (copy ID from the folder's URL)
TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID=
```

- [ ] **Step 4: Install updated deps**

```bash
uv sync
```

Expected: resolves and installs `google-api-python-client` and `google-auth-oauthlib` without errors.

- [ ] **Step 5: Verify config loads cleanly**

```bash
uv run ssm-transcriber config
```

Expected: command prints settings table without errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/transcriber/config.py .env.example
git commit -m "feat(deps+config): add Google Drive upload deps and config settings"
```

---

## Task 2: Auth module — token storage and error type

**Files:**
- Create: `src/transcriber/core/auth.py`
- Create: `tests/unit/test_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_auth.py`:

```python
"""Unit tests for core/auth.py — OAuth token storage and error behaviour."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from transcriber.core.auth import AuthError, _save_credentials, load_drive_credentials


def test_load_drive_credentials_raises_auth_error_when_no_token(tmp_path: Path) -> None:
    """No token file on disk → AuthError pointing to auth command."""
    with patch("transcriber.core.auth.TOKEN_PATH", tmp_path / "missing.json"):
        with pytest.raises(AuthError, match="auth google-drive"):
            load_drive_credentials()


def test_save_credentials_creates_file_and_parent_dirs(tmp_path: Path) -> None:
    """_save_credentials writes to TOKEN_PATH and creates parent dirs."""
    token_path = tmp_path / "sub" / "google_token.json"
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "t"}'

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        _save_credentials(mock_creds)

    assert token_path.exists()
    assert token_path.read_text() == '{"token": "t"}'


def test_load_drive_credentials_raises_auth_error_when_invalid(tmp_path: Path) -> None:
    """Token file exists but credentials are invalid and cannot refresh → AuthError."""
    token_path = tmp_path / "google_token.json"
    token_path.write_text('{"token": "expired"}')

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = None  # cannot refresh

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with patch("transcriber.core.auth.Credentials.from_authorized_user_file", return_value=mock_creds):
            with pytest.raises(AuthError, match="expired"):
                load_drive_credentials()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_auth.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `core/auth.py` does not exist yet.

- [ ] **Step 3: Implement core/auth.py**

Create `src/transcriber/core/auth.py`:

```python
"""Google OAuth token storage and refresh for Drive upload.

TOKEN_PATH holds the refresh token persisted after ``auth google-drive``.
``load_drive_credentials`` is the single entry point for all Drive callers
— it refreshes automatically when the access token expires, and raises
``AuthError`` (→ exit 2) when re-authentication is required.
"""
from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from transcriber.errors import TranscriberError

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_PATH = Path.home() / ".config" / "transcriber" / "google_token.json"


class AuthError(TranscriberError):
    """OAuth token missing, expired, or revoked. CLI maps this to exit 2."""


def load_drive_credentials() -> Credentials:
    """Return valid Drive credentials, refreshing the access token if needed.

    Raises ``AuthError`` when the token file is absent or the refresh token
    is gone — both require the user to re-run ``auth google-drive``.
    """
    if not TOKEN_PATH.exists():
        raise AuthError(
            "Not authenticated with Google Drive. "
            "Run: ssm-transcriber auth google-drive"
        )
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
        return creds
    raise AuthError(
        "Google Drive token expired or revoked. "
        "Rerun: ssm-transcriber auth google-drive"
    )


def authenticate_drive(client_id: str, client_secret: str) -> None:
    """Run browser-based OAuth consent flow and persist the refresh token."""
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        SCOPES,
    )
    creds = flow.run_local_server(port=0)
    _save_credentials(creds)


def _save_credentials(creds: Credentials) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_auth.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/transcriber/core/auth.py tests/unit/test_auth.py
git commit -m "feat(auth): OAuth token storage and AuthError for Drive upload"
```

---

## Task 3: OutputDestination Protocol and DriveDestination

**Files:**
- Create: `src/transcriber/destinations/__init__.py`
- Create: `src/transcriber/destinations/base.py`
- Create: `src/transcriber/destinations/drive.py`
- Create: `tests/unit/test_drive_destination.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_drive_destination.py`:

```python
"""Unit tests for DriveDestination — mocks googleapiclient at the class boundary."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from transcriber.destinations.drive import DriveDestination


def _make_service(web_view_link: str = "https://drive.google.com/file/d/abc/view") -> MagicMock:
    """Return a mock googleapiclient service whose files().create().execute() returns a file dict."""
    mock_service = MagicMock()
    mock_service.files().create().execute.return_value = {
        "id": "abc123",
        "webViewLink": web_view_link,
    }
    return mock_service


def test_upload_returns_drive_url(tmp_path: Path) -> None:
    """Happy path: upload returns the Drive webViewLink."""
    md_file = tmp_path / "session.md"
    md_file.write_text("# Transcript\n")

    mock_service = _make_service("https://drive.google.com/file/d/abc/view")

    with patch("transcriber.destinations.drive.build", return_value=mock_service):
        with patch("transcriber.destinations.drive.load_drive_credentials", return_value=MagicMock()):
            dest = DriveDestination(folder_id="folder-xyz")
            url = dest.upload(md_file, "session.md")

    assert url == "https://drive.google.com/file/d/abc/view"


def test_upload_sends_correct_folder_and_filename(tmp_path: Path) -> None:
    """files().create() is called with the right parent folder and filename."""
    md_file = tmp_path / "out.md"
    md_file.write_text("# hi")

    mock_service = _make_service()
    with patch("transcriber.destinations.drive.build", return_value=mock_service):
        with patch("transcriber.destinations.drive.load_drive_credentials", return_value=MagicMock()):
            DriveDestination(folder_id="folder-abc").upload(md_file, "out.md")

    create_kwargs = mock_service.files().create.call_args.kwargs
    assert create_kwargs["body"]["parents"] == ["folder-abc"]
    assert create_kwargs["body"]["name"] == "out.md"


def test_upload_propagates_api_error(tmp_path: Path) -> None:
    """If the API call raises, DestinationError is raised with the reason."""
    from googleapiclient.errors import HttpError
    from transcriber.destinations.base import DestinationError

    md_file = tmp_path / "out.md"
    md_file.write_text("# hi")

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.status = 404
    mock_service.files().create().execute.side_effect = HttpError(
        resp=mock_response, content=b"Folder not found"
    )

    with patch("transcriber.destinations.drive.build", return_value=mock_service):
        with patch("transcriber.destinations.drive.load_drive_credentials", return_value=MagicMock()):
            with pytest.raises(DestinationError, match="Drive upload failed"):
                DriveDestination(folder_id="bad-folder").upload(md_file, "out.md")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_drive_destination.py -v
```

Expected: `ModuleNotFoundError` — destination modules don't exist yet.

- [ ] **Step 3: Create the destination package**

Create `src/transcriber/destinations/__init__.py` (empty):

```python
```

Create `src/transcriber/destinations/base.py`:

```python
"""OutputDestination Protocol — the upload interface for all destinations.

Java analogue: a single-method interface. Any class with an ``upload``
method of the right signature satisfies it without explicit inheritance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from transcriber.errors import TranscriberError


class DestinationError(TranscriberError):
    """Upload failed or destination misconfigured. CLI maps this to exit 2."""


class OutputDestination(Protocol):
    def upload(self, path: Path, filename: str) -> str:
        """Upload *path* to the destination. Returns a URL or location string."""
        ...
```

Create `src/transcriber/destinations/drive.py`:

```python
"""Google Drive upload destination.

Wraps ``google-api-python-client`` behind the ``OutputDestination`` Protocol.
All auth is delegated to ``core.auth.load_drive_credentials`` — this module
never touches the token file directly.
"""
from __future__ import annotations

from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from transcriber.core.auth import load_drive_credentials
from transcriber.destinations.base import DestinationError


class DriveDestination:
    """Uploads a local file to a Google Drive folder."""

    def __init__(self, folder_id: str) -> None:
        self._folder_id = folder_id

    def upload(self, path: Path, filename: str) -> str:
        """Upload *path* as *filename* into the configured Drive folder.

        Returns the ``webViewLink`` URL. Raises ``DestinationError`` on any
        API failure so the caller always receives a domain error, never a
        raw ``HttpError``.
        """
        creds = load_drive_credentials()
        service = build("drive", "v3", credentials=creds)
        file_metadata = {
            "name": filename,
            "parents": [self._folder_id],
        }
        media = MediaFileUpload(str(path), mimetype="text/markdown")
        try:
            result = (
                service.files()
                .create(body=file_metadata, media_body=media, fields="id,webViewLink")
                .execute()
            )
        except HttpError as exc:
            raise DestinationError(
                f"Drive upload failed: {exc.reason}. "
                f"Transcript saved locally at {path}"
            ) from exc
        return result["webViewLink"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_drive_destination.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
uv run pytest -v
```

Expected: all existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/transcriber/destinations/ tests/unit/test_drive_destination.py
git commit -m "feat(destinations): OutputDestination Protocol + DriveDestination"
```

---

## Task 4: `auth google-drive` CLI subcommand

**Files:**
- Modify: `src/transcriber/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/unit/test_cli.py`:

```python
# ── auth command ─────────────────────────────────────────────────────────────

def test_auth_unknown_provider_exits_2() -> None:
    """`auth s3` is not a supported provider → exit 2."""
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "s3"])
    assert result.exit_code == 2
    assert "unknown provider" in result.stdout.lower()


def test_auth_google_drive_missing_credentials_exits_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`auth google-drive` without OAuth credentials configured → exit 2."""
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "google-drive"])
    assert result.exit_code == 2
    assert "GOOGLE_OAUTH_CLIENT_ID" in result.stdout


def test_auth_google_drive_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """`auth google-drive` with credentials runs authenticate_drive and exits 0."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")

    with patch("transcriber.cli.authenticate_drive") as mock_auth:
        runner = CliRunner()
        result = runner.invoke(app, ["auth", "google-drive"])

    assert result.exit_code == 0
    mock_auth.assert_called_once_with(
        client_id="test-client-id", client_secret="test-client-secret"
    )
    assert "authenticated" in result.stdout.lower()
```

Add the `patch` import at the top of the test file (after the existing imports):

```python
from unittest.mock import patch
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_cli.py::test_auth_unknown_provider_exits_2 \
              tests/unit/test_cli.py::test_auth_google_drive_missing_credentials_exits_2 \
              tests/unit/test_cli.py::test_auth_google_drive_happy_path -v
```

Expected: `FAIL` — `auth` command does not exist.

- [ ] **Step 3: Add the `auth` command to cli.py**

Add these imports to `src/transcriber/cli.py` (after the existing `from transcriber.sources...` imports):

```python
from transcriber.core.auth import AuthError, authenticate_drive
from transcriber.destinations.base import DestinationError
from transcriber.destinations.drive import DriveDestination
```

Add the new command before the `transcribe` command (after the `app = typer.Typer(...)` setup near the top of the command definitions):

```python
@app.command()
def auth(
    provider: Annotated[str, typer.Argument(help="Provider to authenticate ('google-drive')")],
) -> None:
    """Authenticate with a cloud provider and save credentials."""
    if provider != "google-drive":
        console.print(f"[red]error:[/red] Unknown provider {provider!r}. Supported: 'google-drive'")
        raise typer.Exit(code=2)

    client_id = (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        console.print(
            "[red]error:[/red] Google OAuth credentials not configured.\n"
            "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env\n"
            "(see .env.example for setup instructions)"
        )
        raise typer.Exit(code=2)

    authenticate_drive(client_id=client_id, client_secret=client_secret)
    console.print("[green]Google Drive authenticated. Token saved.[/green]")
```

Also add `import os` to the imports in `cli.py` if not already present.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_cli.py::test_auth_unknown_provider_exits_2 \
              tests/unit/test_cli.py::test_auth_google_drive_missing_credentials_exits_2 \
              tests/unit/test_cli.py::test_auth_google_drive_happy_path -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/transcriber/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add auth google-drive subcommand"
```

---

## Task 5: `upload` CLI subcommand

**Files:**
- Modify: `src/transcriber/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/unit/test_cli.py`:

```python
# ── upload command ────────────────────────────────────────────────────────────

def test_upload_missing_file_exits_4(tmp_path: Path) -> None:
    """`upload` with a path that doesn't exist → exit 4."""
    runner = CliRunner()
    result = runner.invoke(app, ["upload", str(tmp_path / "nonexistent.md")])
    assert result.exit_code == 4
    assert "not found" in result.stdout.lower()


def test_upload_no_folder_configured_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`upload` with no folder set → exit 2 with helpful message."""
    md = tmp_path / "session.md"
    md.write_text("# Transcript")
    monkeypatch.delenv("TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID", raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["upload", str(md)])
    assert result.exit_code == 2
    assert "--drive-folder" in result.stdout


def test_upload_happy_path_calls_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: DriveDestination.upload() called with correct args, URL printed."""
    md = tmp_path / "session.md"
    md.write_text("# Transcript")
    monkeypatch.setenv("TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID", "folder-abc")

    mock_dest = MagicMock()
    mock_dest.upload.return_value = "https://drive.google.com/file/d/xyz/view"

    runner = CliRunner()
    with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
        result = runner.invoke(app, ["upload", str(md)])

    assert result.exit_code == 0
    assert "https://drive.google.com/file/d/xyz/view" in result.stdout
    mock_dest.upload.assert_called_once_with(md, "session.md")


def test_upload_drive_folder_flag_overrides_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--drive-folder` overrides TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID."""
    md = tmp_path / "out.md"
    md.write_text("# hi")
    monkeypatch.setenv("TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID", "env-folder")

    mock_dest = MagicMock()
    mock_dest.upload.return_value = "https://drive.google.com/file/d/new/view"

    captured_folder: list[str] = []

    def capture_folder(folder_id: str) -> MagicMock:
        captured_folder.append(folder_id)
        return mock_dest

    runner = CliRunner()
    with patch("transcriber.cli.DriveDestination", side_effect=capture_folder):
        result = runner.invoke(app, ["upload", str(md), "--drive-folder", "cli-folder"])

    assert result.exit_code == 0
    assert captured_folder == ["cli-folder"]
```

Also add `MagicMock` to the import at the top of the test file:

```python
from unittest.mock import MagicMock, patch
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_cli.py::test_upload_missing_file_exits_4 \
              tests/unit/test_cli.py::test_upload_no_folder_configured_exits_2 \
              tests/unit/test_cli.py::test_upload_happy_path_calls_destination \
              tests/unit/test_cli.py::test_upload_drive_folder_flag_overrides_env -v
```

Expected: FAIL — `upload` command does not exist.

- [ ] **Step 3: Add `_resolve_drive_folder` helper and `upload` command to cli.py**

Add `_resolve_drive_folder` as a module-level helper in `cli.py` (just before the command definitions):

```python
def _resolve_drive_folder(cli_folder: str | None) -> str:
    """Return the Drive folder ID from CLI flag or config. Exits 2 if neither set."""
    folder = cli_folder or settings.drive_output_folder_id
    if not folder:
        console.print(
            "[red]error:[/red] No Drive folder configured.\n"
            "Pass --drive-folder FOLDER_ID  or  set TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID in .env"
        )
        raise typer.Exit(code=2)
    return folder
```

Add the `upload` command to `cli.py` (after the `auth` command):

```python
@app.command()
def upload(
    file: Annotated[Path, typer.Argument(help="Transcript file to upload to Google Drive")],
    drive_folder: Annotated[
        str | None,
        typer.Option("--drive-folder", help="Drive folder ID (overrides TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID)"),
    ] = None,
) -> None:
    """Upload an existing transcript file to Google Drive."""
    if not file.exists():
        console.print(f"[red]error:[/red] File not found: {file}")
        raise typer.Exit(code=4)

    folder_id = _resolve_drive_folder(drive_folder)

    try:
        dest = DriveDestination(folder_id=folder_id)
        url = dest.upload(file, file.name)
    except (AuthError, DestinationError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    console.print(f"Uploaded → {url}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_cli.py::test_upload_missing_file_exits_4 \
              tests/unit/test_cli.py::test_upload_no_folder_configured_exits_2 \
              tests/unit/test_cli.py::test_upload_happy_path_calls_destination \
              tests/unit/test_cli.py::test_upload_drive_folder_flag_overrides_env -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/transcriber/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add upload subcommand with folder resolution"
```

---

## Task 6: `--upload-to-drive` flag on `transcribe`

**Files:**
- Modify: `src/transcriber/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/unit/test_cli.py`:

```python
# ── transcribe --upload-to-drive ──────────────────────────────────────────────

def test_transcribe_upload_to_drive_no_folder_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--upload-to-drive` without folder configured → exit 2 before any API call."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake")
    monkeypatch.delenv("TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID", raising=False)
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda _p, _w: (_p, 60.0))

    runner = CliRunner()
    result = runner.invoke(
        app, ["transcribe", str(src), "--budget", "low", "--upload-to-drive", "-y"]
    )
    assert result.exit_code == 2
    assert "--drive-folder" in result.stdout


def test_transcribe_upload_to_drive_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--upload-to-drive` after a successful transcription uploads the .md output."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake")
    monkeypatch.setenv("TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID", "folder-xyz")
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda _p, _w: (_p, 60.0))

    mock_provider = MagicMock()
    mock_provider.transcribe.return_value = MagicMock(
        full_text="Hello world",
        segments=[],
        language="en",
        duration=60.0,
        speech_duration=55.0,
        model_id="nano",
        model_revision="1.0",
        source_url=None,
    )

    mock_dest = MagicMock()
    mock_dest.upload.return_value = "https://drive.google.com/file/d/test/view"

    runner = CliRunner()
    with patch("transcriber.cli.AssemblyAIProvider", return_value=mock_provider):
        with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
            result = runner.invoke(
                app,
                ["transcribe", str(src), "--budget", "low", "--upload-to-drive", "-y"],
            )

    assert result.exit_code == 0
    mock_dest.upload.assert_called_once()
    call_args = mock_dest.upload.call_args
    uploaded_path: Path = call_args.args[0]
    assert uploaded_path.suffix == ".md"
    assert "https://drive.google.com/file/d/test/view" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_cli.py::test_transcribe_upload_to_drive_no_folder_exits_2 \
              tests/unit/test_cli.py::test_transcribe_upload_to_drive_happy_path -v
```

Expected: FAIL — `--upload-to-drive` flag does not exist.

- [ ] **Step 3: Add flags to the `transcribe` command signature in cli.py**

Find the `transcribe` command's parameter list in `cli.py` and add two new parameters (after the existing `no_speakers` parameter):

```python
    upload_to_drive: Annotated[
        bool,
        typer.Option("--upload-to-drive", help="Upload the transcript to Google Drive after transcription"),
    ] = False,
    drive_folder: Annotated[
        str | None,
        typer.Option("--drive-folder", help="Drive folder ID (overrides TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID)"),
    ] = None,
```

In the `transcribe` command body, add the folder validation **near the top** — before any audio extraction or API calls. This gives the user an immediate error rather than failing after 10 minutes of transcription work. Find the earliest point in the command body (after the source is resolved but before `extract_audio` is called) and add:

```python
    # Fail fast: validate Drive folder before doing any transcription work.
    if upload_to_drive:
        _resolve_drive_folder(drive_folder)
```

Then, after the markdown file is written atomically (look for the `atomic.write_text_atomic(...)` call) add the actual upload:

```python
    if upload_to_drive:
        folder_id = _resolve_drive_folder(drive_folder)
        try:
            dest = DriveDestination(folder_id=folder_id)
            drive_url = dest.upload(output_path, output_path.name)
        except (AuthError, DestinationError) as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(code=2) from exc
        console.print(f"Uploaded → {drive_url}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_cli.py::test_transcribe_upload_to_drive_no_folder_exits_2 \
              tests/unit/test_cli.py::test_transcribe_upload_to_drive_happy_path -v
```

Expected: both PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Smoke-test the CLI help to confirm flags appear**

```bash
uv run ssm-transcriber transcribe --help
uv run ssm-transcriber upload --help
uv run ssm-transcriber auth --help
```

Expected: each command shows its new flags/arguments without errors.

- [ ] **Step 7: Commit**

```bash
git add src/transcriber/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add --upload-to-drive and --drive-folder to transcribe"
```

---

## Task 7: README and teaching register

**Files:**
- Modify: `README.md`
- Modify: `docs/learn/journey.md`
- Modify: `docs/learn/prs/README.md`
- Create: `docs/learn/prs/pr-019-drive-upload.md`

> **Note:** the PR number (019) assumes this is the next PR after #18. Adjust if the actual number differs.

- [ ] **Step 1: Add Google Drive setup section to README.md**

Find the existing `## Quick start` section (or equivalent) in `README.md` and add a new `## Google Drive upload` section after it:

```markdown
## Google Drive upload

Transcripts can be uploaded to Google Drive after transcription, or
uploaded separately from an existing file.

### One-time setup

1. Go to [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services** → **Library**. Search for **Google Drive API** and enable it.
2. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**. Choose **Desktop app**, download the JSON, and copy the client ID and secret.
3. Add to your `.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=your-client-id
   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
   TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID=your-folder-id
   ```
   Find a folder ID by opening the folder in Drive — it's the last segment of the URL.
4. Run the one-time auth flow:
   ```bash
   uv run ssm-transcriber auth google-drive
   ```
   A browser window opens for consent. The token is saved to `~/.config/transcriber/google_token.json`.

### Usage

```bash
# Transcribe and upload in one step
uv run ssm-transcriber transcribe "drive://FILE_ID" --budget low --upload-to-drive

# Upload a previously-transcribed file
uv run ssm-transcriber upload ./output/Session20-transcript-2026-05-05.md

# Override the default folder for one run
uv run ssm-transcriber upload ./output/session.md --drive-folder OTHER_FOLDER_ID
```
```

- [ ] **Step 2: Add transcription quick-start section to README.md**

Add a `## Transcription quick-start` section to README.md that shows the end-to-end flow from install to output:

```markdown
## Transcription quick-start

```bash
# Install
git clone https://github.com/manjunath84/SSM-Transcriber
cd SSM-Transcriber
uv sync

# Transcribe a local file (free — uses faster-whisper locally)
# Note: Phase 1 (local faster-whisper) is not yet built.
# The working path today is cloud transcription via AssemblyAI (see below).

# Transcribe via AssemblyAI (requires ASSEMBLYAI_API_KEY in .env)
uv run ssm-transcriber transcribe ./recording.mp4 --budget low

# Transcribe a Google Drive file (public link)
uv run ssm-transcriber transcribe "drive://FILE_ID" --budget low

# See all options
uv run ssm-transcriber transcribe --help
```
```

- [ ] **Step 3: Draft the PR explainer**

Create `docs/learn/prs/pr-019-drive-upload.md` using the template from `docs/learn/README.md`. Fill in:

```markdown
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

- `core/auth.py` — OAuth token storage and refresh; `AuthError` → exit 2
- `destinations/base.py` — `OutputDestination` Protocol + `DestinationError`
- `destinations/drive.py` — `DriveDestination.upload()` wrapping `google-api-python-client`
- `cli.py` — `auth google-drive` subcommand; `upload` subcommand; `--upload-to-drive` + `--drive-folder` flags on `transcribe`
- `config.py` — `TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID` setting; `google_oauth_configured` property
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

## New Python idioms introduced

None beyond what is already documented.

## New AI/ML concepts introduced

None.

## What a reviewer should notice

- The local `.md` is always written before upload is attempted — transcript loss on upload failure is impossible by construction.
- `drive.file` OAuth scope (not `drive`) — the app can only see files it created, not the user's full Drive.
- `DestinationError` and `AuthError` both map to exit 2 (config/setup), consistent with `BudgetError`.
- `_resolve_drive_folder` is shared between `transcribe` and `upload` — folder resolution logic lives in one place.

## Interview angle

- **Story type:** extensible design at low cost — Protocol pattern applied to a new output destination, consistent with existing provider pattern.
- **One-sentence hook:** "Added Drive upload by defining a 3-line OutputDestination Protocol first, so the implementation is a single concrete class with no special-casing in the CLI orchestration."
- **Pointer:** [`interview-prep.md`](../interview-prep.md) — relates to the PreparedMedia DTO boundary design story.

## Further reading

- [`docs/superpowers/specs/2026-05-05-drive-upload-design.md`](../../superpowers/specs/2026-05-05-drive-upload-design.md) — the approved design spec.
- [`pr-003-phase-1-foundations.md`](pr-003-phase-1-foundations.md) — `typing.Protocol` and the Provider pattern this mirrors.
```

- [ ] **Step 4: Update docs/learn/journey.md**

Add a new entry at the top of `journey.md` (before the PR #18 entry):

```markdown
## PR #19 — Drive Upload: transcript → Google Drive

**Merged:** TBD  |  **Branch:** `feat/drive-upload`
**Explainer:** [`prs/pr-019-drive-upload.md`](prs/pr-019-drive-upload.md)

PR #19 adds Google Drive as an upload destination for transcripts. The
`--upload-to-drive` flag on `transcribe` and a standalone `upload` subcommand
both route through a thin `OutputDestination` Protocol, consistent with the
`TranscriptionProvider` pattern established in Phase 5. Auth is a one-time
`auth google-drive` subcommand that persists a refresh token; the Drive
`files.file` scope limits the app to files it creates. The local `.md` is
always written before upload is attempted — transcript loss on failure is
impossible by construction.

---
```

- [ ] **Step 5: Update docs/learn/prs/README.md**

Add PR #19 row to the table (after the #18 row):

```markdown
| #19 | Drive Upload: transcript → Google Drive | feature (impl) | [`pr-019-drive-upload.md`](pr-019-drive-upload.md) |
```

- [ ] **Step 6: Run linting and type-checking**

```bash
uv run ruff check src/ tests/
uv run mypy src/ tests/
```

Expected: no errors.

- [ ] **Step 7: Run full test suite one final time**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add README.md docs/learn/journey.md docs/learn/prs/README.md docs/learn/prs/pr-019-drive-upload.md
git commit -m "docs: README Drive setup + quick-start, teaching register for PR #19"
```

---

## Final: open the PR

```bash
gh pr create \
  --title "feat: Drive upload — transcript → Google Drive via --upload-to-drive and upload subcommand" \
  --body "$(cat <<'EOF'
## Summary

- Adds \`--upload-to-drive\` + \`--drive-folder\` flags to \`transcribe\`
- Adds standalone \`upload\` subcommand for existing transcript files
- Adds \`auth google-drive\` OAuth setup subcommand
- \`OutputDestination\` Protocol makes future destinations (S3, Notion) a one-class add
- README: Google Drive setup guide + transcription quick-start

## Test plan

- [ ] \`uv run pytest\` passes
- [ ] \`uv run ssm-transcriber auth google-drive\` opens browser consent, saves token
- [ ] \`uv run ssm-transcriber upload ./output/SESSION.md\` uploads and prints Drive URL
- [ ] \`uv run ssm-transcriber transcribe "drive://ID" --budget low --upload-to-drive -y\` transcribes and uploads
- [ ] \`uv run ssm-transcriber upload ./output/SESSION.md\` without folder set exits 2 with clear message

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
