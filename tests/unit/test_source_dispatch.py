"""Tests for ``sources/__init__.py``'s ``resolve_source`` dispatcher.

Reject-not-swallow contract: any URI containing ``://`` that doesn't
match a recognised pattern raises ``SourceInputError`` at dispatch
(CLI exit 2). A user who typed ``://`` clearly meant a URL, not a
file path — silently routing to ``LocalSource`` would mislead them
with a "file not found" error.
"""

from __future__ import annotations

import pytest

from transcriber.sources import resolve_source
from transcriber.sources.google_drive import DriveSource
from transcriber.sources.local import LocalSource
from transcriber.sources.youtube import YouTubeSource


def test_resolve_drive_uri() -> None:
    assert resolve_source("drive://1Zdp9aYV") is DriveSource


def test_resolve_full_drive_url() -> None:
    assert resolve_source(
        "https://drive.google.com/file/d/1Zdp9aYV/view"
    ) is DriveSource


def test_resolve_local_path_no_scheme() -> None:
    assert resolve_source("./video.mp4") is LocalSource


def test_resolve_local_path_absolute() -> None:
    assert resolve_source("/Users/foo/video.mp4") is LocalSource


@pytest.mark.parametrize(
    "uri",
    [
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
    ],
)
def test_resolve_youtube_hostnames(uri: str) -> None:
    """All YouTube hostnames route to YouTubeSource. F2's hostname-match
    rule. Phase 2 Slice 1 — captions-only path. Slice 2 (yt-dlp audio
    fallback) reuses the same dispatch arm; the captions-vs-audio
    routing lives inside the source itself."""
    assert resolve_source(uri) is YouTubeSource


def test_resolve_rejects_unknown_https_host() -> None:
    with pytest.raises(ValueError, match="URI scheme not supported"):
        resolve_source("https://example.com/foo")


def test_resolve_rejects_other_scheme() -> None:
    with pytest.raises(ValueError, match="URI scheme not supported"):
        resolve_source("s3://bucket/key")


def test_resolve_rejects_vimeo() -> None:
    """Vimeo isn't on the roadmap; reject-not-swallow keeps the failure
    mode loud rather than letting a "file not found" mislead."""
    with pytest.raises(ValueError, match="URI scheme not supported"):
        resolve_source("https://vimeo.com/123456")
