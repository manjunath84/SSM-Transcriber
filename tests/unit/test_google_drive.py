"""Tests for ``sources/google_drive.py`` — URL parsing + DriveSource.

URL parsing is a pure function over the five forms documented in
``specs/2026-05-04-drive-source-passthrough/requirements.md`` §"Reference
calls (verbatim)". The tests dogfood that section: each form pasted
verbatim from the spec.
"""

from __future__ import annotations

import pytest
import responses

from transcriber.core.workspace import RunWorkspace
from transcriber.sources.base import PreparedMedia
from transcriber.sources.google_drive import DriveSource, _extract_file_id

_VALID_ID = "1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd"
_REMOTE_URL = (
    f"https://drive.usercontent.google.com/download"
    f"?id={_VALID_ID}&export=download&confirm=t"
)


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


@responses.activate
def test_drive_source_prepare_returns_correct_prepared_media() -> None:
    """Default-field shape after prepare(). With no --title, title is
    auto-resolved from the CDN's Content-Disposition header (option (c),
    PLAN.md Phase 4 Slice 3); all other fields take their dataclass
    defaults."""
    responses.add(
        responses.GET,
        _REMOTE_URL,
        status=200,
        headers={
            "content-disposition": 'attachment; filename="Session17.mp4"'
        },
    )
    workspace = RunWorkspace()
    media = DriveSource.prepare(f"drive://{_VALID_ID}", workspace)

    assert isinstance(media, PreparedMedia)
    assert media.kind == "google_drive"
    assert media.original_uri == f"drive://{_VALID_ID}"
    assert media.local_path is None
    assert media.remote_url == _REMOTE_URL
    assert media.title == "Session17"
    assert media.duration_seconds is None
    assert media.extra == {"drive_file_id": _VALID_ID}


def test_drive_source_prepare_canonicalises_full_drive_url() -> None:
    """Whatever URL form the user passes, original_uri normalises to
    drive://FILE_ID and remote_url to the public-download canonical form.
    Passing title= explicitly bypasses the network probe — this test is
    about URL canonicalisation, not titling."""
    workspace = RunWorkspace()
    media = DriveSource.prepare(
        f"https://drive.google.com/file/d/{_VALID_ID}/view?usp=sharing",
        workspace,
        title="Session 17",
    )

    assert media.original_uri == f"drive://{_VALID_ID}"
    assert media.remote_url == _REMOTE_URL


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
    it lands in PreparedMedia.title for the formatter to pick up. When
    --title is set the network probe is skipped — no HTTP mock required."""
    workspace = RunWorkspace()
    media = DriveSource.prepare(
        f"drive://{_VALID_ID}", workspace, title="Session 17"
    )
    assert media.title == "Session 17"


# ---------------------------------------------------------------------------
# Title auto-resolution from Content-Disposition (option (c) — see
# docs/PLAN.md "Phase 4 — Slice 3"). When the user doesn't pass --title,
# DriveSource.prepare does a streamed GET against the public Drive download
# URL and parses the Content-Disposition filename. No OAuth, no GCP project.
# Same code path AssemblyAI uses to fetch the file, so headers we parse
# here are the headers AssemblyAI sees.
# ---------------------------------------------------------------------------


@responses.activate
def test_drive_source_prepare_resolves_title_from_content_disposition() -> None:
    """Vendor-API contract: Drive's CDN sends e.g.
    ``content-disposition: attachment; filename="Session17.mp4"`` on the
    public download URL. The exact header bytes pinned here come from a
    curl probe of a real Drive file (235 MB, anyone-with-link), captured
    in specs/2026-05-04-drive-source-passthrough/requirements.md.

    Per the CLAUDE.md guardrail (PR #12 lesson): pin byte-for-byte to
    catch silent regressions if Google's CDN changes the header shape."""
    responses.add(
        responses.GET,
        _REMOTE_URL,
        status=200,
        headers={
            "content-disposition": 'attachment; filename="Session17.mp4"'
        },
    )
    workspace = RunWorkspace()
    media = DriveSource.prepare(f"drive://{_VALID_ID}", workspace)
    assert media.title == "Session17"


@responses.activate
def test_drive_source_prepare_falls_through_when_no_content_disposition() -> None:
    """File no longer publicly shared (or any non-CD response): caller
    falls through to the file-ID stem at the CLI/formatter layer.
    media.title stays None — same behaviour as Slice 2 shipped."""
    responses.add(responses.GET, _REMOTE_URL, status=200, headers={})
    workspace = RunWorkspace()
    media = DriveSource.prepare(f"drive://{_VALID_ID}", workspace)
    assert media.title is None


@responses.activate
def test_drive_source_prepare_falls_through_on_non_200() -> None:
    """403 / 404 from Drive (revoked sharing, deleted file): swallow and
    fall through. The user will hit the same condition during the actual
    transcribe-fetch and get a clear error from AssemblyAI; no point
    failing twice."""
    responses.add(responses.GET, _REMOTE_URL, status=404)
    workspace = RunWorkspace()
    media = DriveSource.prepare(f"drive://{_VALID_ID}", workspace)
    assert media.title is None


@responses.activate
def test_drive_source_prepare_falls_through_on_network_error() -> None:
    """Offline / DNS failure / timeout: don't block transcribe. The user
    might be offline composing a job to run later — accepting the file ID
    stem is strictly better than exit-2-ing on a network probe."""
    from requests.exceptions import ConnectionError as ReqConnectionError

    responses.add(responses.GET, _REMOTE_URL, body=ReqConnectionError("boom"))
    workspace = RunWorkspace()
    media = DriveSource.prepare(f"drive://{_VALID_ID}", workspace)
    assert media.title is None


@pytest.mark.parametrize(
    ("filename", "reason"),
    [
        # Uploader-chosen filename with embedded newline corrupts YAML
        # frontmatter (literal \n splits ``title:`` scalar across lines,
        # downstream YAML parsers raise ScannerError).
        ('foo%0Abar.mp4', "newline"),
        # Leading dot would produce a hidden output file on Unix; the
        # --title path explicitly rejects this and we must too.
        ('.hidden.mp4', "leading-dot"),
        # ``..`` is explicitly rejected on the --title path (validation
        # spec case 26a). Auto-resolved path must not let it through.
        ('foo..bar.mp4', "double-dot"),
        # NUL byte in filename — would corrupt YAML and shell expansion.
        ('foo%00bar.mp4', "nul"),
        # DEL (0x7f) — outside printable ASCII, rejected by _validate_title's
        # control-character check.
        ('foo%7Fbar.mp4', "del-char"),
    ],
)
@responses.activate
def test_drive_source_prepare_rejects_hostile_filenames(
    filename: str, reason: str,
) -> None:
    """Anyone-with-link Drive sources mean the uploader is potentially
    untrusted — the user transcribing a friend's shared video inherits
    whatever filename the third-party uploader chose. Hostile or quirky
    values must fail-soft to None (caller falls through to file-ID stem),
    not corrupt YAML / create hidden files / pass path-traversal markers.

    Mirrors the rejections that ``--title`` already enforces via
    ``_validate_title`` — keeps the two ingestion paths symmetric."""
    responses.add(
        responses.GET,
        _REMOTE_URL,
        status=200,
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )
    workspace = RunWorkspace()
    media = DriveSource.prepare(f"drive://{_VALID_ID}", workspace)
    assert media.title is None, f"hostile filename ({reason}) leaked through"


@responses.activate
def test_drive_source_prepare_resolves_via_canonicalised_url() -> None:
    """User pasted a full Drive URL form. prepare() canonicalises to the
    drive.usercontent.google.com download URL before probing — verify the
    probe hits that canonical URL, not whatever the user pasted."""
    responses.add(
        responses.GET,
        _REMOTE_URL,
        status=200,
        headers={
            "content-disposition": 'attachment; filename="Session17.mp4"'
        },
    )
    workspace = RunWorkspace()
    media = DriveSource.prepare(
        f"https://drive.google.com/file/d/{_VALID_ID}/view?usp=sharing",
        workspace,
    )
    assert media.title == "Session17"
