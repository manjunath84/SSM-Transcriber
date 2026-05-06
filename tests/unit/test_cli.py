"""CLI integration tests — exit-code matrix.

Covers case 23 (exit codes for each error path) with subsystems mocked
where needed. Case 24 (filename collision suffix-increment) is verified
via the unit tests for ``core/atomic.resolve_collision``; the CLI just
calls that function with the planned output path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from transcriber.cli import app


def test_unsupported_format_exits_2(tmp_path: Path) -> None:
    """`--format txt` is not in Slice 1's supported set → exit 2."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", str(src), "--format", "txt", "--budget", "low"])
    assert result.exit_code == 2
    assert "only --format md" in result.stdout


def test_default_budget_free_blocks_paid_provider_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even with the key configured, `--budget free` (default) blocks the
    paid call → exit 2 with the documented message."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    # Bypass real audio extract so we reach the budget gate.
    monkeypatch.setattr(
        "transcriber.cli.extract_audio",
        lambda _path, _ws: (_path, 60.0),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", str(src), "-y"])  # default --budget=free
    assert result.exit_code == 2
    assert "paid provider" in result.stdout.lower()


def test_missing_key_with_low_budget_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--budget low` but no ASSEMBLYAI_API_KEY → Gate 1 fails → exit 2."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")

    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "transcriber.cli.extract_audio",
        lambda _path, _ws: (_path, 60.0),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", str(src), "--budget", "low", "-y"])
    assert result.exit_code == 2
    assert "ASSEMBLYAI_API_KEY" in result.stdout


def test_directory_source_exits_2(tmp_path: Path) -> None:
    """A directory passed as the source raises ValueError in LocalSource;
    CLI maps it to exit 2 (config/usage error), not exit 4 (local error)."""
    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", str(tmp_path), "--budget", "low", "-y"])
    assert result.exit_code == 2


def test_audio_extract_error_exits_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ffmpeg/ffprobe failure → AudioExtractError → exit 4 (local error)."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")

    from transcriber.core.audio import AudioExtractError

    def _boom(_path: object, _ws: object) -> tuple[Path, float]:
        raise AudioExtractError("ffmpeg crashed")

    monkeypatch.setattr("transcriber.cli.extract_audio", _boom)

    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", str(src), "--budget", "low", "-y"])
    assert result.exit_code == 4
    assert "ffmpeg crashed" in result.stdout


def test_provider_error_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AssemblyAI 401 / retry exhaustion / polling timeout → ProviderError
    → exit 3 (provider error)."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr(
        "transcriber.cli.extract_audio",
        lambda _path, _ws: (_path, 60.0),
    )

    from transcriber.providers.base import ProviderError

    class _BoomProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(self, *_args: object, **_kwargs: object) -> None:
            raise ProviderError("AssemblyAI HTTP 401: bad key")

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _BoomProvider)

    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", str(src), "--budget", "low", "-y"])
    assert result.exit_code == 3
    assert "401" in result.stdout


def test_atomic_write_oserror_exits_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disk full / EACCES on the final write → OSError → exit 4."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr(
        "transcriber.cli.extract_audio",
        lambda _path, _ws: (_path, 60.0),
    )

    from transcriber.providers.base import Segment, TranscriptResult

    class _OkProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(self, *_args: object, **_kwargs: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=1.0,
                model="universal-3-pro",
                job_id="j",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    def _boom_write(_path: object, _content: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("transcriber.cli.atomic.write_text_atomic", _boom_write)

    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", str(src), "--budget", "low", "-y"])
    assert result.exit_code == 4
    assert "disk full" in result.stdout


def test_user_declines_prompt_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No -y, user types 'n' at the prompt → cancelled cleanly, exit 0."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr(
        "transcriber.cli.extract_audio",
        lambda _path, _ws: (_path, 60.0),
    )
    # _confirm_or_decline returns False → budget_check returns False → cancel.
    monkeypatch.setattr("transcriber.cli._confirm_or_decline", lambda _msg: False)

    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", str(src), "--budget", "low"])
    assert result.exit_code == 0
    assert "Cancelled" in result.stdout or "cancelled" in result.stdout


def test_invalid_budget_value_rejected_at_typer_parse(tmp_path: Path) -> None:
    """``--budget paind`` (typo'd "paid") must NOT silently authorise paid
    use. Typer's Enum binding rejects the value at parse time before any
    subsystem runs. Without the Enum (when ``budget`` was a free-form
    ``str``), only ``"free"`` was blocked and any other string fell
    through Gate 2 to the spend path."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")

    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", str(src), "--budget", "paind", "-y"])
    # Typer/Click maps invalid Enum values to its usage-error code (2).
    assert result.exit_code == 2
    # In newer typer versions stderr is folded into stdout; either way the
    # invalid value or a typer "Invalid value" hint must be visible.
    assert "paind" in result.output or "Invalid value" in result.output


def test_eof_on_prompt_treated_as_decline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closed stdin (Ctrl-D, piped input ended) raises EOFError from
    Confirm.ask. _confirm_or_decline must treat that as a decline so the
    user gets exit 0, not an uncaught traceback + exit 1."""
    from transcriber.cli import _confirm_or_decline

    def _eof_ask(*_args: object, **_kwargs: object) -> bool:
        raise EOFError("stdin closed")

    monkeypatch.setattr("transcriber.cli.Confirm.ask", _eof_ask)
    assert _confirm_or_decline("Proceed?") is False


# ---------------------------------------------------------------------------
# Title sanitization helpers (Slice 2). _validate_title returns the display
# form (whitespace stripped at edges, internal preserved). _title_to_stem
# collapses internal whitespace to '-' for filenames.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Session 17", "Session 17"),
        ("  trimmed  ", "trimmed"),
        ("internal  whitespace  preserved", "internal  whitespace  preserved"),
        ("v1.2 release notes", "v1.2 release notes"),
    ],
)
def test_validate_title_accepts_safe_titles(title: str, expected: str) -> None:
    from transcriber.cli import _validate_title

    assert _validate_title(title) == expected


@pytest.mark.parametrize(
    "unsafe",
    [
        "../foo",
        "a/b",
        "back\\slash",
        ".hidden",
        "ok..bad",
        "with\0null",
    ],
)
def test_validate_title_rejects_unsafe_characters(unsafe: str) -> None:
    """Path-traversal protection — atomic.write_text_atomic creates parent
    directories on demand, so an unsanitized --title '../foo' would write
    outside settings.output_dir. Validation case 26a explicitly tests this.
    """
    from transcriber.cli import _validate_title

    with pytest.raises(ValueError, match="unsafe filename"):
        _validate_title(unsafe)


@pytest.mark.parametrize(
    "unsafe",
    [
        "line1\nline2",   # newline corrupts YAML title flow scalar
        "tab\there",       # tab control char
        "ret\rurn",        # carriage return
        "bell\x07",        # bell
        "del\x7f",         # DEL (0x7f) — outside the printable ASCII range
    ],
)
def test_validate_title_rejects_control_characters(unsafe: str) -> None:
    """Control characters (\\x00-\\x1f, \\x7f) corrupt YAML frontmatter
    when written to ``title:`` as a flow scalar — a literal newline
    splits the value mid-scalar, a carriage return swaps in unicode
    direction, etc. NUL was already covered by the unsafe-substring
    check; widen to all C0 controls + DEL."""
    from transcriber.cli import _validate_title

    with pytest.raises(ValueError, match="unsafe filename"):
        _validate_title(unsafe)


def test_validate_title_rejects_empty_after_strip() -> None:
    from transcriber.cli import _validate_title

    with pytest.raises(ValueError, match="unsafe filename|empty"):
        _validate_title("   ")


@pytest.mark.parametrize(
    "title,expected_stem",
    [
        ("Session 17", "Session-17"),
        ("v1.2 release notes", "v1.2-release-notes"),
        ("internal  whitespace", "internal-whitespace"),
        ("trimmed", "trimmed"),
    ],
)
def test_title_to_stem_collapses_whitespace_to_dashes(
    title: str, expected_stem: str
) -> None:
    """Whitespace in --title becomes '-' in the filename; YAML title
    preserves the original (validation case 26b)."""
    from transcriber.cli import _title_to_stem

    assert _title_to_stem(title) == expected_stem


def test_title_to_stem_assumes_input_already_validated() -> None:
    """_title_to_stem does no validation — it expects a string that has
    already passed _validate_title. Tests document the order so a future
    caller doesn't accidentally swap them."""
    from transcriber.cli import _title_to_stem

    # No validation happens here; the contract is "validate first, then collapse".
    assert _title_to_stem("path with spaces") == "path-with-spaces"


# ---------------------------------------------------------------------------
# Drive source — end-to-end CLI scenarios (Slice 2).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "drive_uri",
    [
        "drive://1Zdp9aYV",
        "https://drive.google.com/file/d/1Zdp9aYV/view",
        "https://drive.google.com/file/d/1Zdp9aYV/view?usp=sharing",
        "https://drive.google.com/open?id=1Zdp9aYV",
    ],
)
def test_drive_happy_path_with_title(
    drive_uri: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """transcribe <drive-uri> --title 'Session 17' --budget low -y →
    writes Session-17-{date}.md with frontmatter title 'Session 17' and
    canonical source_uri 'drive://1Zdp9aYV' (regardless of input form).
    extract_audio NOT called (Drive path).

    Validation case 25 — every accepted URL form must round-trip to
    identical output."""
    from transcriber.providers.base import Segment, TranscriptResult

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    extract_called: list[str] = []

    def _record_extract(*_args: object, **_kwargs: object) -> tuple[None, float]:
        extract_called.append("CALLED")
        return (None, 0.0)

    monkeypatch.setattr("transcriber.cli.extract_audio", _record_extract)

    class _OkProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(self, *_args: object, **_kwargs: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=1.0,
                model="universal-3-pro",
                job_id="drive-job",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "transcribe",
            drive_uri,
            "--title",
            "Session 17",
            "--budget",
            "low",
            "-y",
        ],
    )
    assert result.exit_code == 0, result.output
    assert extract_called == []  # Drive path skips ffmpeg
    written = list(tmp_path.glob("Session-17-*.md"))
    assert len(written) == 1, f"expected one Session-17-*.md, got {written}"
    content = written[0].read_text(encoding="utf-8")
    assert "title: Session 17" in content
    # Canonical drive://FILE_ID in source_uri regardless of which URL form
    # was passed (validation case 25's central assertion).
    assert "source_uri: drive://1Zdp9aYV" in content
    assert "source_kind: google_drive" in content
    # Validation case 20 (review I2): the Drive notify message must signal
    # per-minute billing + dashboard. Lock the production wording so a
    # future "improvement" that drops either substring breaks the suite.
    assert "per-minute" in result.output
    assert "dashboard" in result.output.lower()


def test_drive_happy_path_no_title_uses_file_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No --title → output filename uses the file ID."""
    from transcriber.providers.base import Segment, TranscriptResult

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    class _OkProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(self, *_args: object, **_kwargs: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=1.0,
                model="universal-3-pro",
                job_id="drive-job",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["transcribe", "drive://1Zdp9aYV", "--budget", "low", "-y"],
    )
    assert result.exit_code == 0, result.output
    written = list(tmp_path.glob("1Zdp9aYV-*.md"))
    assert len(written) == 1


def test_unknown_uri_scheme_exits_2(tmp_path: Path) -> None:
    """transcribe https://example.com/foo → exit 2 with 'URI scheme not
    supported' (NOT a 'file not found' fallthrough to LocalSource)."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["transcribe", "https://example.com/foo", "--budget", "low", "-y"],
    )
    assert result.exit_code == 2
    assert "URI scheme not supported" in result.output


def test_drive_budget_free_still_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive sources don't bypass Gate 2."""
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    runner = CliRunner()
    result = runner.invoke(
        app, ["transcribe", "drive://1Zdp9aYV", "-y"]  # default --budget=free
    )
    assert result.exit_code == 2
    assert "paid provider" in result.output.lower()


def test_drive_no_api_key_still_blocks_at_gate_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation case 21 (review I3): Drive sources don't bypass Gate 1.

    Without ASSEMBLYAI_API_KEY, a Drive transcription must reject at the
    gate (exit 2 with the Gate 1 message), NOT proceed to AssemblyAI and
    surface a wire-level 401. Locks the contract so a future refactor of
    the Drive branch (e.g., short-circuiting Gate 1 when cost_summary is
    set) breaks the suite instead of shipping a silent regression.
    """
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["transcribe", "drive://1Zdp9aYV", "--budget", "low", "-y"],
    )
    assert result.exit_code == 2
    assert "ASSEMBLYAI_API_KEY" in result.output


def test_drive_unsanitized_title_exits_2() -> None:
    """transcribe drive://X --title '../foo' → exit 2 (sanitization)."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["transcribe", "drive://1Zdp9aYV", "--title", "../foo", "--budget", "low", "-y"],
    )
    assert result.exit_code == 2
    assert "unsafe filename" in result.output


def test_local_path_uploads_extracted_wav_not_source_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1 regression: after extract_audio, the provider must receive the
    canonical 16 kHz mono WAV path — NOT the original source file.

    Without the dataclasses.replace(media, local_path=wav_path) swap in
    the CLI's local-path branch, the provider uploads media.local_path
    (the .mp4 / .m4a the user passed) instead of the WAV extract_audio
    produced. AssemblyAI accepts any audio container, so the regression
    is invisible at runtime past mocks but breaks Slice 1's
    "extract → normalised WAV → upload" contract silently.
    """
    from transcriber.providers.base import Segment, TranscriptResult
    from transcriber.sources.base import PreparedMedia

    src = tmp_path / "video.mp4"
    src.write_bytes(b"")
    wav_in_workspace = tmp_path / "ws" / "extracted.wav"
    wav_in_workspace.parent.mkdir()
    wav_in_workspace.write_bytes(b"")

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setattr(
        "transcriber.cli.extract_audio",
        lambda _path, _ws: (wav_in_workspace, 60.0),
    )

    received_media: list[PreparedMedia] = []

    class _RecordingProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(
            self, media: PreparedMedia, *_args: object, **_kwargs: object
        ) -> TranscriptResult:
            received_media.append(media)
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=1.0,
                model="universal-3-pro",
                job_id="local-job",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _RecordingProvider)

    runner = CliRunner()
    result = runner.invoke(
        app, ["transcribe", str(src), "--budget", "low", "-y"]
    )
    assert result.exit_code == 0, result.output
    assert len(received_media) == 1
    # The provider must have seen the EXTRACTED WAV in the workspace,
    # not the original .mp4 the user passed on the command line. This is
    # the C1 invariant.
    assert received_media[0].local_path == wav_in_workspace
    assert received_media[0].local_path != src
    # Output filename must use the SOURCE stem ('video'), NOT the WAV
    # stem ('extracted'). After the C1 swap, ``media.local_path`` is the
    # workspace WAV — using ``media.local_path.stem`` for the filename
    # would silently regress Slice 1 to write ``extracted-DATE.md``
    # instead of ``video-DATE.md`` for any non-WAV input.
    written = list(tmp_path.glob("video-*.md"))
    assert len(written) == 1, (
        f"expected one video-*.md (Slice 1 source-stem behaviour), "
        f"got {[p.name for p in tmp_path.glob('*.md')]}"
    )


# ── auth command ─────────────────────────────────────────────────────────────

def test_auth_unknown_provider_exits_2() -> None:
    """`auth s3` is not a supported provider → exit 2."""
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "s3"])
    assert result.exit_code == 2
    assert "unknown provider" in result.stdout.lower()


def test_auth_google_drive_missing_credentials_exits_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`auth google-drive` without OAuth credentials configured → exit 2."""
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "google-drive"])
    assert result.exit_code == 2
    assert "GOOGLE_OAUTH_CLIENT_ID" in result.stdout


def test_auth_google_drive_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """`auth google-drive` with credentials runs authenticate_drive and exits 0."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")

    with patch("transcriber.cli.authenticate_drive") as mock_auth:
        runner = CliRunner()
        result = runner.invoke(app, ["auth", "google-drive"])

    assert result.exit_code == 0
    mock_auth.assert_called_once_with(
        client_id="test-client-id", client_secret="test-client-secret"
    )
    assert "authenticated" in result.stdout.lower()


# ── upload command ────────────────────────────────────────────────────────────

def test_upload_missing_file_exits_4(tmp_path: Path) -> None:
    """`upload` with a path that doesn't exist → exit 4 (local file error).

    Exit 4 matches the established matrix: local-file errors (missing source,
    ffmpeg failure) all map to 4.  The task spec draft said exit 1, but the
    project matrix is {0, 2, 3, 4} — "file not found" is a local-file error,
    same category as the ``transcribe`` command's FileNotFoundError → exit 4
    path (cli.py lines 253-256).
    """
    runner = CliRunner()
    result = runner.invoke(app, ["upload", str(tmp_path / "nonexistent.md")])
    assert result.exit_code == 4
    assert "not found" in result.stdout.lower()


def test_upload_no_folder_configured_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`upload` with no folder set → exit 2 with helpful message.

    Uses setattr on the singleton because drive_output_folder_id is a
    pydantic-settings field baked in at construction time; setenv would
    not affect a singleton already created (and a teammate with
    TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID in their .env would see a flaky
    failure without this explicit override).
    """
    md = tmp_path / "session.md"
    md.write_text("# Transcript")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", None)

    runner = CliRunner()
    result = runner.invoke(app, ["upload", str(md)])
    assert result.exit_code == 2
    assert "--drive-folder" in result.stdout


def test_upload_happy_path_calls_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: DriveDestination.upload() called with correct args, URL printed.

    Uses setattr on the singleton because drive_output_folder_id is a
    pydantic-settings field baked in at construction time.
    """
    md = tmp_path / "session.md"
    md.write_text("# Transcript")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "folder-abc")

    mock_dest = MagicMock()
    mock_dest.upload.return_value = "https://drive.google.com/file/d/xyz/view"

    runner = CliRunner()
    with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
        result = runner.invoke(app, ["upload", str(md)])

    assert result.exit_code == 0
    assert "https://drive.google.com/file/d/xyz/view" in result.stdout
    mock_dest.upload.assert_called_once_with(md, "session.md")


def test_upload_drive_folder_flag_overrides_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--drive-folder` overrides TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID.

    Uses setattr on the singleton because drive_output_folder_id is a
    pydantic-settings field baked in at construction time.
    """
    md = tmp_path / "out.md"
    md.write_text("# hi")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "env-folder")

    mock_dest = MagicMock()
    mock_dest.upload.return_value = "https://drive.google.com/file/d/new/view"

    captured_folder: list[str] = []

    def capture_folder(folder_id: str) -> MagicMock:
        captured_folder.append(folder_id)
        return mock_dest

    runner = CliRunner()
    with patch("transcriber.cli.DriveDestination", side_effect=capture_folder):
        result = runner.invoke(app, ["upload", str(md), "--drive-folder", "cli-folder"])

    assert result.exit_code == 0
    assert captured_folder == ["cli-folder"]
