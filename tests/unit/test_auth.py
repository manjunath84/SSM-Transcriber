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
        with patch(
            "transcriber.core.auth.Credentials.from_authorized_user_file",
            return_value=mock_creds,
        ):
            with pytest.raises(AuthError, match="expired"):
                load_drive_credentials()
