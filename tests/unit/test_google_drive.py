"""Tests for ``sources/google_drive.py`` — URL parsing + DriveSource.

URL parsing is a pure function over the five forms documented in
``specs/2026-05-04-drive-source-passthrough/requirements.md`` §"Reference
calls (verbatim)". The tests dogfood that section: each form pasted
verbatim from the spec.
"""

from __future__ import annotations

import pytest

from transcriber.sources.google_drive import _extract_file_id

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
