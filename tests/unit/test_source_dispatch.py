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


def test_resolve_rejects_unknown_scheme_youtube() -> None:
    """YouTube lands in Phase 2; until then, reject-not-swallow."""
    with pytest.raises(ValueError, match="URI scheme not supported"):
        resolve_source("https://youtube.com/watch?v=abc")


def test_resolve_rejects_unknown_https_host() -> None:
    with pytest.raises(ValueError, match="URI scheme not supported"):
        resolve_source("https://example.com/foo")


def test_resolve_rejects_other_scheme() -> None:
    with pytest.raises(ValueError, match="URI scheme not supported"):
        resolve_source("s3://bucket/key")
