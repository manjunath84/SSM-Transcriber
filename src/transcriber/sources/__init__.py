"""Source dispatch — pattern-match on URI shape and return the source.

Reject-not-swallow design: any URI containing ``://`` that doesn't match
a recognised source pattern raises ``SourceInputError`` at dispatch. The
CLI catches and maps to exit 2. The alternative — silently routing
unrecognised ``://`` URIs to ``LocalSource`` — would mislead the user
with a "file not found" error when the real problem is "URL scheme
not supported."

Future sources (Phase 2 YouTube, Slice 3 OAuth-Drive) slot in as new
pattern arms above the catch-all ``SourceInputError``.
"""

from __future__ import annotations

from transcriber.sources.base import SourceInputError
from transcriber.sources.google_drive import DriveSource
from transcriber.sources.local import LocalSource


def resolve_source(uri: str) -> type[DriveSource] | type[LocalSource]:
    """Return the ``Source`` class that handles ``uri``.

    Raises ``SourceInputError`` (subclass of ``ValueError``) if ``uri``
    is URL-shaped but doesn't match any known source pattern.
    """
    if uri.startswith("drive://") or uri.startswith(
        ("https://drive.google.com/", "http://drive.google.com/")
    ):
        return DriveSource
    if "://" in uri:
        raise SourceInputError(
            f"URI scheme not supported: {uri!r}. "
            "Expected: a local file path, drive://FILE_ID, "
            "or a Google Drive URL (https://drive.google.com/...)."
        )
    return LocalSource


__all__ = ["resolve_source"]
