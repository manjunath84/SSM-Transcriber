"""Source dispatch — pattern-match on URI shape and return the source.

Reject-not-swallow design: any URI containing ``://`` that doesn't match
a recognised source pattern raises ``SourceInputError`` at dispatch. The
CLI catches and maps to exit 2. The alternative — silently routing
unrecognised ``://`` URIs to ``LocalSource`` — would mislead the user
with a "file not found" error when the real problem is "URL scheme
not supported."

Phase 2 Slice 1 added YouTube. The captions-vs-audio routing for
Slice 2's yt-dlp fallback lives inside ``YouTubeSource`` itself —
dispatch only needs to know "this is a YouTube URL." Slice 3
(OAuth Drive) will reuse the existing Drive arm.
"""

from __future__ import annotations

from urllib.parse import urlparse

from transcriber.sources.base import SourceInputError
from transcriber.sources.google_drive import DriveSource
from transcriber.sources.local import LocalSource
from transcriber.sources.youtube import YouTubeSource

# F2 hostname-match rule (docs/PLAN.md §F2). The host comparison is
# done after lowercasing via ``urlparse.hostname`` so case quirks in
# user input (``YOUTUBE.com``) don't bypass the arm.
_YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
)


def resolve_source(
    uri: str,
) -> type[DriveSource] | type[LocalSource] | type[YouTubeSource]:
    """Return the ``Source`` class that handles ``uri``.

    Raises ``SourceInputError`` (subclass of ``ValueError``) if ``uri``
    is URL-shaped but doesn't match any known source pattern.
    """
    if uri.startswith("drive://") or uri.startswith(
        ("https://drive.google.com/", "http://drive.google.com/")
    ):
        return DriveSource

    # Hostname-match for YouTube (any of the eight URL forms enumerated
    # in the spec's §"Reference calls (verbatim)").
    if "://" in uri:
        try:
            host = (urlparse(uri).hostname or "").lower()
        except ValueError:
            host = ""
        if host in _YOUTUBE_HOSTS:
            return YouTubeSource

        raise SourceInputError(
            f"URI scheme not supported: {uri!r}. "
            "Expected: a local file path, drive://FILE_ID, "
            "a Google Drive URL (https://drive.google.com/...), "
            "or a YouTube URL (https://youtu.be/... or "
            "https://youtube.com/watch?v=...)."
        )
    return LocalSource


__all__ = ["resolve_source"]
