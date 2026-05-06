"""Google OAuth token storage and refresh for Drive upload.

TOKEN_PATH holds the refresh token persisted after ``auth google-drive``.
``load_drive_credentials`` is the single entry point for all Drive callers
— it refreshes automatically when the access token expires, and raises
``AuthError`` (→ exit 2) when re-authentication is required.
"""
from __future__ import annotations

import os
from pathlib import Path

from google.auth import exceptions as google_auth_exceptions
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

    Raises:
        AuthError: if the token file is absent, corrupt, unreadable, or if
            the refresh token is gone or cannot be refreshed — all require
            re-running ``auth google-drive``.
    """
    if not TOKEN_PATH.exists():
        raise AuthError(
            "Not authenticated with Google Drive. "
            "Run: ssm-transcriber auth google-drive"
        )
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    except (ValueError, OSError) as exc:
        raise AuthError(
            "Google Drive token file is corrupt or unreadable. "
            "Rerun: ssm-transcriber auth google-drive"
        ) from exc
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except (
            google_auth_exceptions.RefreshError,
            google_auth_exceptions.TransportError,
        ) as exc:
            raise AuthError(
                "Google Drive token could not be refreshed. "
                "Rerun: ssm-transcriber auth google-drive"
            ) from exc
        # In-memory creds are valid for this run even if persistence fails.
        # Surface the persistence problem actionably rather than crashing
        # with a raw OSError (read-only home, full disk, sticky-bit dir).
        try:
            _save_credentials(creds)
        except OSError as exc:
            raise AuthError(
                f"Drive token refreshed but could not be saved to {TOKEN_PATH}: {exc}. "
                "Check permissions on ~/.config/transcriber/."
            ) from exc
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
    tmp = TOKEN_PATH.with_suffix(".tmp")
    # Sweep any leftover .tmp from a crashed prior write so the O_EXCL
    # below doesn't trip on it.
    tmp.unlink(missing_ok=True)
    # O_CREAT|O_WRONLY|O_EXCL with mode 0o600 ensures the file is never
    # world/group-readable, even briefly. write_text() would create the
    # file under the process umask first (typical default 0o022 → mode
    # 0o644), leaving a window before chmod() narrows permissions.
    fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(creds.to_json())
        # replace() is inside the try so a failure (cross-device link,
        # sticky-bit dir, target is a directory) cleans up the .tmp
        # rather than leaving a token-bearing file at 0o600 on disk.
        tmp.replace(TOKEN_PATH)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
