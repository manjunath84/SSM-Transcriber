"""Google OAuth token storage and refresh for Drive upload.

TOKEN_PATH holds the refresh token persisted after ``auth google-drive``.
``load_drive_credentials`` is the single entry point for all Drive callers
— it refreshes automatically when the access token expires, and raises
``AuthError`` (→ exit 2) when re-authentication is required.
"""
from __future__ import annotations

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
        try:
            creds.refresh(Request())
        except google_auth_exceptions.RefreshError as exc:
            raise AuthError(
                "Google Drive token could not be refreshed. "
                "Rerun: ssm-transcriber auth google-drive"
            ) from exc
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
    TOKEN_PATH.chmod(0o600)
