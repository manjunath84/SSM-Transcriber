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
    assert oct(token_path.stat().st_mode)[-3:] == "600"


def test_load_drive_credentials_raises_auth_error_when_invalid(tmp_path: Path) -> None:
    """Token file exists but credentials are invalid and cannot refresh → AuthError."""
    token_path = tmp_path / "google_token.json"
    token_path.write_text('{"token": "expired"}')

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = None  # cannot refresh

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with patch(
            "transcriber.core.auth.Credentials.from_authorized_user_file",
            return_value=mock_creds,
        ):
            with pytest.raises(AuthError, match="expired"):
                load_drive_credentials()


def test_load_drive_credentials_returns_valid_creds(tmp_path: Path) -> None:
    """Token file exists and credentials are still valid → return them directly."""
    token_path = tmp_path / "google_token.json"
    token_path.write_text('{"token": "valid"}')

    mock_creds = MagicMock()
    mock_creds.valid = True

    creds_patcher = patch(
        "transcriber.core.auth.Credentials.from_authorized_user_file",
        return_value=mock_creds,
    )
    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with creds_patcher:
            result = load_drive_credentials()

    assert result is mock_creds


def test_load_drive_credentials_refreshes_when_expired(tmp_path: Path) -> None:
    """Expired token with refresh_token available → refreshes and saves updated creds."""
    token_path = tmp_path / "google_token.json"
    token_path.write_text('{"token": "expired"}')

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "refresh-tok"
    mock_creds.to_json.return_value = '{"token": "refreshed"}'

    creds_patcher = patch(
        "transcriber.core.auth.Credentials.from_authorized_user_file",
        return_value=mock_creds,
    )
    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with creds_patcher:
            with patch("transcriber.core.auth.Request") as mock_request:
                result = load_drive_credentials()

    assert result is mock_creds
    mock_creds.refresh.assert_called_once_with(mock_request.return_value)
    assert token_path.read_text() == '{"token": "refreshed"}'


def test_load_drive_credentials_raises_auth_error_when_refresh_fails(tmp_path: Path) -> None:
    """RefreshError during token refresh → AuthError (not an uncaught exception)."""
    from google.auth import exceptions as google_auth_exceptions

    token_path = tmp_path / "google_token.json"
    token_path.write_text('{"token": "expired"}')

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "refresh-tok"
    mock_creds.refresh.side_effect = google_auth_exceptions.RefreshError("revoked")

    creds_patcher = patch(
        "transcriber.core.auth.Credentials.from_authorized_user_file", return_value=mock_creds
    )
    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with creds_patcher:
            with pytest.raises(AuthError, match="could not be refreshed"):
                load_drive_credentials()
