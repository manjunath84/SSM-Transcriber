"""Google Drive upload destination.

Wraps ``google-api-python-client`` behind the ``OutputDestination`` Protocol.
All auth is delegated to ``core.auth.load_drive_credentials`` — this module
never touches the token file directly.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from transcriber.core.auth import load_drive_credentials
from transcriber.destinations.base import DestinationError


class DriveDestination:
    """Uploads a local file to a Google Drive folder."""

    def __init__(self, folder_id: str) -> None:
        if not folder_id:
            raise DestinationError("Drive folder ID must not be empty")
        self._folder_id = folder_id

    def upload(self, path: Path, filename: str) -> str:
        """Upload *path* as *filename* into the configured Drive folder.

        *filename* lets the caller control the name shown in Drive independently
        of the local path — useful when the workspace temp name differs from the
        desired output name.

        Returns the ``webViewLink`` URL. Raises ``DestinationError`` on any
        API or transport failure so the caller always receives a domain error.
        """
        creds = load_drive_credentials()
        file_metadata = {
            "name": filename,
            "parents": [self._folder_id],
        }
        mimetype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        media = MediaFileUpload(str(path), mimetype=mimetype)
        try:
            service = build("drive", "v3", credentials=creds)
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
        url = result.get("webViewLink")
        if not url:
            raise DestinationError(
                "Drive upload succeeded but response is missing webViewLink. "
                f"Transcript saved locally at {path}"
            )
        return url
