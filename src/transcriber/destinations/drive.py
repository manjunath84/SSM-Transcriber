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
