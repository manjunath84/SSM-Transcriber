"""Unit tests for DriveDestination — mocks googleapiclient at the class boundary."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.http import MediaFileUpload

from transcriber.destinations.base import DestinationError, OutputDestination
from transcriber.destinations.drive import DriveDestination

_LOAD_CREDS = "transcriber.destinations.drive.load_drive_credentials"
_BUILD = "transcriber.destinations.drive.build"


def _make_service(web_view_link: str = "https://drive.google.com/file/d/abc/view") -> MagicMock:
    """Return a mock service whose files().create().execute() returns a file dict."""
    mock_service = MagicMock()
    mock_service.files().create().execute.return_value = {
        "id": "abc123",
        "webViewLink": web_view_link,
    }
    return mock_service


def test_drive_destination_satisfies_output_destination_protocol() -> None:
    """DriveDestination structurally satisfies OutputDestination Protocol."""
    dest: OutputDestination = DriveDestination(folder_id="test")  # mypy checks this
    assert hasattr(dest, "upload")


@pytest.mark.parametrize("folder_id", ["", "   ", "\t\n", "\n  \t"])
def test_drive_destination_rejects_empty_or_whitespace_folder(folder_id: str) -> None:
    """Constructor-level guard: empty or whitespace-only folder_id → DestinationError.

    The CLI's _resolve_drive_folder strips and exits 2 before reaching this
    constructor, but a non-CLI Python caller (e.g. a future programmatic API)
    must still get a clear failure rather than passing parents=[''] to Drive.
    """
    with pytest.raises(DestinationError, match="must not be empty"):
        DriveDestination(folder_id=folder_id)


def test_upload_returns_drive_url(tmp_path: Path) -> None:
    """Happy path: upload returns the Drive webViewLink."""
    md_file = tmp_path / "session.md"
    md_file.write_text("# Transcript\n")

    mock_service = _make_service("https://drive.google.com/file/d/abc/view")

    with patch(_BUILD, return_value=mock_service):
        with patch(_LOAD_CREDS, return_value=MagicMock()):
            dest = DriveDestination(folder_id="folder-xyz")
            url = dest.upload(md_file, "session.md")

    assert url == "https://drive.google.com/file/d/abc/view"


def test_upload_sends_correct_folder_and_filename(tmp_path: Path) -> None:
    """files().create() is called with the right parent folder and filename."""
    md_file = tmp_path / "out.md"
    md_file.write_text("# hi")

    mock_service = _make_service()
    with patch(_BUILD, return_value=mock_service):
        with patch(_LOAD_CREDS, return_value=MagicMock()):
            DriveDestination(folder_id="folder-abc").upload(md_file, "out.md")

    create_kwargs = mock_service.files().create.call_args.kwargs
    assert create_kwargs["body"]["parents"] == ["folder-abc"]
    assert create_kwargs["body"]["name"] == "out.md"
    assert create_kwargs["fields"] == "id,webViewLink"
    assert isinstance(create_kwargs["media_body"], MediaFileUpload)
    # _filename is a private attr of MediaFileUpload — pinned because the
    # public API doesn't expose the source path. If google-api-python-client
    # renames it, this test breaks with an unrelated AttributeError; that's
    # a deliberate canary.
    assert create_kwargs["media_body"]._filename == str(md_file)


def test_upload_propagates_api_error(tmp_path: Path) -> None:
    """If the API call raises, DestinationError is raised with the reason."""
    from googleapiclient.errors import HttpError

    md_file = tmp_path / "out.md"
    md_file.write_text("# hi")

    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.status = 404
    mock_service.files().create().execute.side_effect = HttpError(
        resp=mock_response, content=b"Folder not found"
    )

    with patch(_BUILD, return_value=mock_service):
        with patch(_LOAD_CREDS, return_value=MagicMock()):
            with pytest.raises(DestinationError, match="Drive upload failed"):
                DriveDestination(folder_id="bad-folder").upload(md_file, "out.md")


def test_upload_propagates_transport_error(tmp_path: Path) -> None:
    """Network failures during the upload raise DestinationError, not a raw exception."""
    from google.auth import exceptions as google_auth_exceptions

    md_file = tmp_path / "out.md"
    md_file.write_text("# hi")

    mock_service = MagicMock()
    mock_service.files().create().execute.side_effect = google_auth_exceptions.TransportError(
        "connection reset"
    )

    with patch(_BUILD, return_value=mock_service):
        with patch(_LOAD_CREDS, return_value=MagicMock()):
            with pytest.raises(DestinationError, match="network error"):
                DriveDestination(folder_id="folder-abc").upload(md_file, "out.md")


def test_upload_wraps_missing_file_as_destination_error(tmp_path: Path) -> None:
    """bug_003 regression: MediaFileUpload's __init__ calls open(path, 'rb')
    eagerly, so a missing/unreadable path raises FileNotFoundError. That
    constructor must run inside the try block so the resulting OSError is
    caught and wrapped as DestinationError with the documented 'Transcript
    saved locally at <path>' recovery hint, not leaked past the
    AuthError/DestinationError contract.

    Realistic trigger: in the ``upload`` subcommand, ``load_drive_credentials``
    runs inside ``upload()`` and may do a network token refresh
    (~hundreds of ms typical), widening the TOCTOU window between the
    CLI's ``file.is_file()`` check and the MediaFileUpload construction
    enough for a parallel cleanup process to delete the file."""
    missing = tmp_path / "vanished.md"  # intentionally never created
    with patch(_LOAD_CREDS, return_value=MagicMock()):
        with pytest.raises(DestinationError, match="Transcript saved locally"):
            DriveDestination(folder_id="folder-abc").upload(missing, "vanished.md")


def test_upload_propagates_httplib2_error(tmp_path: Path) -> None:
    """DNS failure / captive-portal hijack raises DestinationError, not a stack trace.

    httplib2.HttpLib2Error is NOT a subclass of OSError, so without an explicit
    catch the user would see a raw traceback instead of the recovery hint.
    """
    import httplib2

    md_file = tmp_path / "out.md"
    md_file.write_text("# hi")

    mock_service = MagicMock()
    mock_service.files().create().execute.side_effect = httplib2.ServerNotFoundError(
        "nodename nor servname provided, or not known"
    )

    with patch(_BUILD, return_value=mock_service):
        with patch(_LOAD_CREDS, return_value=MagicMock()):
            with pytest.raises(DestinationError, match="network error"):
                DriveDestination(folder_id="folder-abc").upload(md_file, "out.md")


def test_upload_propagates_invalid_json_error(tmp_path: Path) -> None:
    """Google returning HTML during an outage raises DestinationError, not a stack trace.

    googleapiclient.errors.InvalidJsonError is a sibling (not subclass) of
    HttpError under the gapi_errors.Error parent — so it needs its own catch.
    """
    from googleapiclient.errors import InvalidJsonError

    md_file = tmp_path / "out.md"
    md_file.write_text("# hi")

    mock_service = MagicMock()
    mock_service.files().create().execute.side_effect = InvalidJsonError(
        "<html>500 Internal Server Error</html>"
    )

    with patch(_BUILD, return_value=mock_service):
        with patch(_LOAD_CREDS, return_value=MagicMock()):
            with pytest.raises(DestinationError, match="Drive upload failed"):
                DriveDestination(folder_id="folder-abc").upload(md_file, "out.md")


def test_upload_raises_when_webviewlink_missing(tmp_path: Path) -> None:
    """If Drive response omits webViewLink, DestinationError is raised."""
    md_file = tmp_path / "session.md"
    md_file.write_text("# Transcript\n")

    mock_service = MagicMock()
    mock_service.files().create().execute.return_value = {"id": "abc123"}  # no webViewLink

    with patch(_BUILD, return_value=mock_service):
        with patch(_LOAD_CREDS, return_value=MagicMock()):
            with pytest.raises(DestinationError, match="missing webViewLink"):
                DriveDestination(folder_id="folder-xyz").upload(md_file, "session.md")
