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


def test_load_drive_credentials_raises_auth_error_when_transport_error(tmp_path: Path) -> None:
    """TransportError (network failure) during refresh → AuthError, not raw exception."""
    from google.auth import exceptions as google_auth_exceptions

    token_path = tmp_path / "google_token.json"
    token_path.write_text('{"token": "expired"}')

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "refresh-tok"
    mock_creds.refresh.side_effect = google_auth_exceptions.TransportError("network error")

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with patch(
            "transcriber.core.auth.Credentials.from_authorized_user_file",
            return_value=mock_creds,
        ):
            with pytest.raises(AuthError, match="could not be refreshed"):
                load_drive_credentials()


def test_load_drive_credentials_raises_auth_error_on_corrupt_file(tmp_path: Path) -> None:
    """Corrupt or unreadable token file raises AuthError, not a raw ValueError."""
    token_path = tmp_path / "google_token.json"
    token_path.write_text("not valid json at all {{{")

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with patch(
            "transcriber.core.auth.Credentials.from_authorized_user_file",
            side_effect=ValueError("invalid json"),
        ):
            with pytest.raises(AuthError, match="corrupt or unreadable"):
                load_drive_credentials()


def test_save_credentials_is_atomic(tmp_path: Path) -> None:
    """_save_credentials writes via a .tmp file then renames — no world-readable window."""
    token_path = tmp_path / "sub" / "google_token.json"
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "t"}'

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        _save_credentials(mock_creds)

    assert token_path.exists()
    assert not token_path.with_suffix(".tmp").exists(), ".tmp must be cleaned up after rename"
    assert token_path.read_text() == '{"token": "t"}'
    assert oct(token_path.stat().st_mode)[-3:] == "600"


def test_save_credentials_overwrites_stale_tmp_from_crashed_prior_write(tmp_path: Path) -> None:
    """A leftover .tmp from a crashed prior write must not block re-auth.

    Without the leading ``tmp.unlink(missing_ok=True)`` in _save_credentials,
    the next O_EXCL open would raise FileExistsError and the user would have
    to manually find and delete the stale file before re-authenticating.
    """
    token_path = tmp_path / "google_token.json"
    stale_tmp = token_path.with_suffix(".tmp")
    stale_tmp.write_text('{"stale": "from-crash"}')

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "fresh"}'

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        _save_credentials(mock_creds)

    assert token_path.read_text() == '{"token": "fresh"}'
    assert not stale_tmp.exists()


def test_save_credentials_cleans_up_tmp_on_write_failure(tmp_path: Path) -> None:
    """If creds.to_json() raises mid-write, the .tmp must be removed (no leak)."""
    token_path = tmp_path / "google_token.json"
    mock_creds = MagicMock()
    mock_creds.to_json.side_effect = RuntimeError("disk full")

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with pytest.raises(RuntimeError, match="disk full"):
            _save_credentials(mock_creds)

    assert not token_path.exists()
    assert not token_path.with_suffix(".tmp").exists(), (
        ".tmp must be cleaned up after a mid-write exception"
    )


def test_load_drive_credentials_save_failure_raises_auth_error(tmp_path: Path) -> None:
    """Refresh succeeds but _save_credentials raises OSError → AuthError, not raw OSError.

    Read-only home / full disk / sticky-bit dir would otherwise crash with a
    raw traceback after a successful refresh, leaving the user confused
    (in-memory creds are valid; only persistence broke).
    """
    token_path = tmp_path / "google_token.json"
    token_path.write_text('{"token": "expired"}')

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "refresh-tok"
    mock_creds.to_json.return_value = '{"token": "refreshed"}'

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with patch(
            "transcriber.core.auth.Credentials.from_authorized_user_file",
            return_value=mock_creds,
        ):
            with patch("transcriber.core.auth.Request"):
                with patch(
                    "transcriber.core.auth._save_credentials",
                    side_effect=OSError("Read-only file system"),
                ):
                    with pytest.raises(AuthError, match="could not be saved"):
                        load_drive_credentials()


def test_authenticate_drive_calls_flow_with_correct_config(tmp_path: Path) -> None:
    """authenticate_drive constructs InstalledAppFlow with the right client config shape."""
    from transcriber.core.auth import authenticate_drive

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "new"}'
    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_creds

    token_path = tmp_path / "google_token.json"

    with patch("transcriber.core.auth.TOKEN_PATH", token_path):
        with patch(
            "transcriber.core.auth.InstalledAppFlow.from_client_config",
            return_value=mock_flow,
        ) as mock_from_config:
            authenticate_drive(client_id="cid", client_secret="csecret")

    call_config = mock_from_config.call_args[0][0]
    assert call_config["installed"]["client_id"] == "cid"
    assert call_config["installed"]["client_secret"] == "csecret"
    assert "auth_uri" in call_config["installed"]
    assert "token_uri" in call_config["installed"]
    mock_flow.run_local_server.assert_called_once_with(port=0)
    assert token_path.exists()
