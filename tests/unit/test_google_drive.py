"""Tests for ``sources/google_drive.py`` — URL parsing + DriveSource.

URL parsing is a pure function over the five forms documented in
``specs/2026-05-04-drive-source-passthrough/requirements.md`` §"Reference
calls (verbatim)". The tests dogfood that section: each form pasted
verbatim from the spec.
"""

from __future__ import annotations

import pytest

from transcriber.core.workspace import RunWorkspace
from transcriber.sources.base import PreparedMedia
from transcriber.sources.google_drive import DriveSource, _extract_file_id

_VALID_ID = "1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd"


@pytest.mark.parametrize(
    "uri",
    [
        f"drive://{_VALID_ID}",
        f"https://drive.google.com/file/d/{_VALID_ID}/view",
        f"https://drive.google.com/file/d/{_VALID_ID}/view?usp=sharing",
        f"https://drive.google.com/open?id={_VALID_ID}",
        f"https://drive.google.com/uc?export=download&id={_VALID_ID}",
    ],
)
def test_extract_file_id_accepts_all_documented_forms(uri: str) -> None:
    assert _extract_file_id(uri) == _VALID_ID


def test_extract_file_id_rejects_empty_drive_uri() -> None:
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("drive://")


def test_extract_file_id_rejects_drive_uri_with_invalid_chars() -> None:
    """Drive file IDs are URL-safe base64 (alnum + - + _). Fail loud on
    anything else rather than passing garbage through to AssemblyAI."""
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("drive://has spaces")


def test_extract_file_id_rejects_drive_uri_with_trailing_newline() -> None:
    """Without using ``fullmatch`` instead of ``match`` + ``$``, a
    trailing ``\\n`` would slip past validation (the ``$`` anchor matches
    before-final-newline by default). Lock that down — pasted IDs from
    text with trailing newlines must reject loudly."""
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("drive://abc\n")


def test_extract_file_id_rejects_file_d_with_empty_segment() -> None:
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("https://drive.google.com/file/d//view")


def test_extract_file_id_rejects_open_without_id_param() -> None:
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("https://drive.google.com/open")


def test_extract_file_id_rejects_drive_url_with_unrecognised_path() -> None:
    """https://drive.google.com/folders/X — folders aren't in the supported
    URL forms; reject loudly so a user pasting a folder doesn't silently
    land in the wrong code path."""
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("https://drive.google.com/folders/abc")


@pytest.mark.parametrize(
    "folder_uri",
    [
        # Direct folder URL forms that Drive's "Get link" emits.
        "https://drive.google.com/drive/folders/1ABC123",
        "https://drive.google.com/drive/u/0/folders/1ABC123",
        "https://drive.google.com/drive/u/1/folders/1ABC123?usp=sharing",
    ],
)
def test_extract_file_id_rejects_folder_urls_with_clearer_message(
    folder_uri: str,
) -> None:
    """Drive folder URLs (containing /folders/) reject with a folder-specific
    message rather than the generic "must include /file/d/<ID> or ?id=<ID>".
    A user who pastes a folder URL should see they pasted the wrong type of
    link, not be confused about URL form requirements.

    Note: open?id=<FOLDER_ID> is indistinguishable from open?id=<FILE_ID>
    via the URL alone (both are URL-safe-base64 strings); that case
    requires an OAuth metadata fetch (Slice 3) to detect."""
    with pytest.raises(ValueError) as excinfo:
        _extract_file_id(folder_uri)
    # Match "folder" as a word in the error message (not just the URI),
    # i.e. require some phrase like "appears to point to a folder" or
    # "folder URL". Using re.search on str(exc.value) without this
    # constraint would match the URI itself which contains "folders/".
    assert "appears to point to a folder" in str(excinfo.value), (
        f"expected folder-specific message, got: {excinfo.value}"
    )


# ---------------------------------------------------------------------------
# DriveSource.prepare — wraps the parser into a PreparedMedia.
# ---------------------------------------------------------------------------


def test_drive_source_prepare_returns_correct_prepared_media() -> None:
    workspace = RunWorkspace()
    media = DriveSource.prepare(f"drive://{_VALID_ID}", workspace)

    assert isinstance(media, PreparedMedia)
    assert media.kind == "google_drive"
    assert media.original_uri == f"drive://{_VALID_ID}"
    assert media.local_path is None
    assert media.remote_url == (
        f"https://drive.usercontent.google.com/download"
        f"?id={_VALID_ID}&export=download&confirm=t"
    )
    assert media.title is None  # CLI fills in from --title
    assert media.duration_seconds is None
    assert media.extra == {"drive_file_id": _VALID_ID}


def test_drive_source_prepare_canonicalises_full_drive_url() -> None:
    """Whatever URL form the user passes, original_uri normalises to
    drive://FILE_ID and remote_url to the public-download canonical form."""
    workspace = RunWorkspace()
    media = DriveSource.prepare(
        f"https://drive.google.com/file/d/{_VALID_ID}/view?usp=sharing",
        workspace,
    )

    assert media.original_uri == f"drive://{_VALID_ID}"
    assert media.remote_url == (
        f"https://drive.usercontent.google.com/download"
        f"?id={_VALID_ID}&export=download&confirm=t"
    )


def test_drive_source_prepare_raises_on_unparseable_uri() -> None:
    """Defence-in-depth: DriveSource.prepare validates even though
    resolve_source already filters at dispatch (Task 4). Tests call
    DriveSource directly without going through dispatch."""
    workspace = RunWorkspace()
    with pytest.raises(ValueError, match="could not extract"):
        DriveSource.prepare("drive://", workspace)


def test_drive_source_prepare_raises_on_non_drive_host() -> None:
    workspace = RunWorkspace()
    with pytest.raises(ValueError, match="could not extract"):
        DriveSource.prepare("https://example.com/foo", workspace)


def test_drive_source_prepare_threads_title_kwarg() -> None:
    """CLI passes the validated --title through to prepare(title=...);
    it lands in PreparedMedia.title for the formatter to pick up."""
    workspace = RunWorkspace()
    media = DriveSource.prepare(
        f"drive://{_VALID_ID}", workspace, title="Session 17"
    )
    assert media.title == "Session 17"
