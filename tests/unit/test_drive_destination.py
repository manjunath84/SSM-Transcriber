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
