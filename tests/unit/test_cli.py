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
from transcriber.core.auth import AuthError
from transcriber.destinations.base import DestinationError


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
                provider="assemblyai",
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
# Title sanitization helpers (Slice 2 + post-PR-#19 follow-up).
# validate_title returns the display form (whitespace stripped at edges,
# internal preserved). title_to_stem collapses internal whitespace to '-'
# for filenames. Both moved from cli.py to core/title.py so the Drive
# source layer can share them (bug_004 fix — auto-resolved filenames
# from Content-Disposition headers must hit the same validator the
# --title path uses, otherwise an uploader-chosen ``foo\nbar.mp4`` from
# Drive corrupts YAML frontmatter).
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
    from transcriber.core.title import validate_title

    assert validate_title(title) == expected


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
    from transcriber.core.title import validate_title

    with pytest.raises(ValueError, match="unsafe filename"):
        validate_title(unsafe)


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
    from transcriber.core.title import validate_title

    with pytest.raises(ValueError, match="unsafe filename"):
        validate_title(unsafe)


def test_validate_title_rejects_empty_after_strip() -> None:
    from transcriber.core.title import validate_title

    with pytest.raises(ValueError, match="unsafe filename|empty"):
        validate_title("   ")


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
    from transcriber.core.title import title_to_stem

    assert title_to_stem(title) == expected_stem


def test_title_to_stem_assumes_input_already_validated() -> None:
    """title_to_stem does no validation — it expects a string that has
    already passed validate_title. Tests document the order so a future
    caller doesn't accidentally swap them."""
    from transcriber.core.title import title_to_stem

    # No validation happens here; the contract is "validate first, then collapse".
    assert title_to_stem("path with spaces") == "path-with-spaces"


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
                provider="assemblyai",
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
    """No --title → CDN title probe returns None (mocked, to keep the
    unit-test hermetic — see bug_012 in the post-PR-#19 review) → output
    filename falls back to the file ID."""
    from transcriber.providers.base import Segment, TranscriptResult

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    # Without this, DriveSource.prepare() makes a real network call to
    # drive.usercontent.google.com — bug_012 from the ultrareview.
    monkeypatch.setattr(
        "transcriber.sources.google_drive._fetch_drive_filename",
        lambda _u: None,
    )

    class _OkProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(self, *_args: object, **_kwargs: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=1.0,
                provider="assemblyai",
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


def test_drive_auto_resolved_title_produces_dash_stem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bug_004 (CLI side): when DriveSource auto-resolves a title with
    internal whitespace ('Session 17' from Content-Disposition), the
    output filename must collapse whitespace to '-' identically to the
    --title path. Closes the convergence gap where
    ``--title "Session 17"`` produced ``Session-17-DATE.md`` but the
    auto-resolved path produced ``Session 17-DATE.md``."""
    from transcriber.providers.base import Segment, TranscriptResult

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setattr(
        "transcriber.sources.google_drive._fetch_drive_filename",
        lambda _u: "Session 17",
    )

    class _OkProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(self, *_args: object, **_kwargs: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=1.0,
                provider="assemblyai",
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
    # Dash-collapsed — matches what --title "Session 17" produces.
    assert list(tmp_path.glob("Session-17-*.md"))
    # Literal-space form must not appear.
    assert not list(tmp_path.glob("Session 17-*.md"))


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
    # Mock the CDN title probe — DriveSource.prepare() runs before the
    # budget gate, so without this the test makes a real network call
    # (bug_012 from the ultrareview).
    monkeypatch.setattr(
        "transcriber.sources.google_drive._fetch_drive_filename",
        lambda _u: None,
    )
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
    # Mock the CDN title probe — same reason as test_drive_budget_free
    # above; bug_012 from the ultrareview.
    monkeypatch.setattr(
        "transcriber.sources.google_drive._fetch_drive_filename",
        lambda _u: None,
    )
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
                provider="assemblyai",
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


def test_auth_google_drive_authenticate_error_exits_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`auth google-drive` when authenticate_drive raises → exit 2 with message, not traceback."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")

    with patch(
        "transcriber.cli.authenticate_drive",
        side_effect=OSError("port already in use"),
    ):
        result = CliRunner().invoke(app, ["auth", "google-drive"])

    assert result.exit_code == 2
    assert "authentication failed" in result.stdout.lower()


# ── upload command ────────────────────────────────────────────────────────────

def test_upload_missing_file_exits_4(tmp_path: Path) -> None:
    """`upload` with a path that doesn't exist → exit 4 (local file error).

    Exit 4 matches the established matrix: local-file errors (missing source,
    ffmpeg failure) all map to 4. The task spec draft said exit 1, but the
    project matrix is {0, 2, 3, 4} — "file not found" is a local-file error,
    same category as the ``transcribe`` command's FileNotFoundError → exit 4
    path.
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
    with patch("transcriber.cli.DriveDestination", return_value=mock_dest) as MockDest:
        result = runner.invoke(app, ["upload", str(md)])

    assert result.exit_code == 0
    assert "https://drive.google.com/file/d/xyz/view" in result.stdout
    MockDest.assert_called_once_with(folder_id="folder-abc")
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


def test_upload_auth_error_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`upload` when DriveDestination raises AuthError → exit 2 with the error message."""
    md = tmp_path / "f.md"
    md.write_text("# hi")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "folder-abc")

    mock_dest = MagicMock()
    mock_dest.upload.side_effect = AuthError("token expired")

    with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
        result = CliRunner().invoke(app, ["upload", str(md)])

    assert result.exit_code == 2
    assert "token expired" in result.stdout


def test_upload_destination_error_exits_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`upload` when DriveDestination raises DestinationError → exit 4 (file preserved).

    Different exit code from AuthError (2 = config to fix) lets scripts
    distinguish "fix auth" from "transient upload failure, retry".
    """
    md = tmp_path / "f.md"
    md.write_text("# hi")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "folder-abc")

    mock_dest = MagicMock()
    mock_dest.upload.side_effect = DestinationError("Drive upload failed: 403")

    with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
        result = CliRunner().invoke(app, ["upload", str(md)])

    assert result.exit_code == 4
    assert "Drive upload failed" in result.stdout


@pytest.mark.parametrize("flag_value", ["   ", "\t", "\n  \t"])
def test_upload_whitespace_only_drive_folder_flag_exits_2(
    flag_value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--drive-folder '   '`` is treated as unset → exit 2 with helpful message.

    Without the .strip() in _resolve_drive_folder, a whitespace-only flag
    would slip past the truthiness check and propagate to DriveDestination,
    which would raise DestinationError later (after construction).
    """
    md = tmp_path / "f.md"
    md.write_text("# hi")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", None)

    result = CliRunner().invoke(app, ["upload", str(md), "--drive-folder", flag_value])
    assert result.exit_code == 2
    assert "--drive-folder" in result.stdout


# ── transcribe --upload-to-drive ──────────────────────────────────────────────

def test_transcribe_upload_to_drive_no_folder_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--upload-to-drive` without folder configured → exit 2 before any API call.

    Specifically verifies that extract_audio is NOT called — the fail-fast
    check fires before any audio or transcription work begins.
    """
    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", None)

    extract_called: list[str] = []

    def _record_extract(*_args: object, **_kwargs: object) -> tuple[object, float]:
        extract_called.append("called")
        return (_args[0], 60.0)

    monkeypatch.setattr("transcriber.cli.extract_audio", _record_extract)

    runner = CliRunner()
    result = runner.invoke(
        app, ["transcribe", str(src), "--budget", "low", "--upload-to-drive", "-y"]
    )
    assert result.exit_code == 2
    assert "--drive-folder" in result.stdout
    assert extract_called == [], "extract_audio must not be called before folder check passes"


def test_transcribe_upload_to_drive_auth_failfast_before_paid_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--upload-to-drive` when not authenticated → exit 2 before any API call.

    load_drive_credentials is called early (fail-fast). The budget gate
    must NOT fire first — the user should not be asked to confirm cost
    when they haven't authenticated yet.
    """
    from transcriber.core.auth import AuthError

    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "folder-abc")

    extract_called: list[str] = []

    def _record_extract(*_args: object, **_kwargs: object) -> tuple[object, float]:
        extract_called.append("called")
        return (_args[0], 60.0)

    monkeypatch.setattr("transcriber.cli.extract_audio", _record_extract)
    def _raise_auth() -> None:
        raise AuthError("Run: ssm-transcriber auth google-drive")

    monkeypatch.setattr("transcriber.cli.load_drive_credentials", _raise_auth)

    result = CliRunner().invoke(
        app, ["transcribe", str(src), "--budget", "low", "--upload-to-drive", "-y"]
    )

    assert result.exit_code == 2
    assert "auth google-drive" in result.stdout
    assert extract_called == [], "extract_audio must not be called before auth check passes"


def test_transcribe_upload_to_drive_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--upload-to-drive` after a successful transcription uploads the .md output."""
    from transcriber.providers.base import TranscriptResult

    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "folder-xyz")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda _p, _w: (_p, 60.0))

    mock_provider = MagicMock()
    mock_provider.transcribe.return_value = TranscriptResult(
        text="Hello world",
        segments=[],
        language="en",
        duration_seconds=60.0,
        provider="assemblyai",
        model="universal-3-pro",
        job_id="j",
    )

    mock_dest = MagicMock()
    mock_dest.upload.return_value = "https://drive.google.com/file/d/test/view"

    runner = CliRunner()
    with patch("transcriber.cli.load_drive_credentials"):
        with patch("transcriber.cli.AssemblyAIProvider", return_value=mock_provider):
            with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
                result = runner.invoke(
                    app,
                    ["transcribe", str(src), "--budget", "low", "--upload-to-drive", "-y"],
                )

    assert result.exit_code == 0
    mock_dest.upload.assert_called_once()
    call_args = mock_dest.upload.call_args
    uploaded_path: Path = call_args.args[0]
    assert uploaded_path.suffix == ".md"
    assert "https://drive.google.com/file/d/test/view" in result.stdout


def test_transcribe_upload_to_drive_folder_flag_overrides_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--drive-folder passed to transcribe overrides TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID."""
    from transcriber.providers.base import TranscriptResult

    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "env-folder")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda _p, _w: (_p, 60.0))

    mock_provider = MagicMock()
    mock_provider.transcribe.return_value = TranscriptResult(
        text="hi",
        segments=[],
        language="en",
        duration_seconds=60.0,
        provider="assemblyai",
        model="universal-3-pro",
        job_id="j",
    )

    captured_folder: list[str] = []
    mock_dest = MagicMock()
    mock_dest.upload.return_value = "https://drive.google.com/file/d/x/view"

    def _capture(folder_id: str) -> MagicMock:
        captured_folder.append(folder_id)
        return mock_dest

    runner = CliRunner()
    with patch("transcriber.cli.load_drive_credentials"):
        with patch("transcriber.cli.AssemblyAIProvider", return_value=mock_provider):
            with patch("transcriber.cli.DriveDestination", side_effect=_capture):
                result = runner.invoke(
                    app,
                    [
                        "transcribe", str(src), "--budget", "low",
                        "--upload-to-drive", "--drive-folder", "cli-folder", "-y",
                    ],
                )

    assert result.exit_code == 0, result.output
    assert captured_folder == ["cli-folder"]


def test_transcribe_upload_to_drive_auth_error_post_extract_exits_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AuthError raised by upload (after a paid AssemblyAI call) → exit 4, recovery hint printed.

    This is the race-condition path: pre-flight load_drive_credentials
    succeeded, then the token was revoked between fail-fast and upload. The
    user has paid for transcription and the .md is on disk — different
    category from the pre-flight AuthError (exit 2), which is the "config
    broken, no work done" case.
    """
    from transcriber.providers.base import TranscriptResult

    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "folder-xyz")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda _p, _w: (_p, 60.0))

    mock_provider = MagicMock()
    mock_provider.transcribe.return_value = TranscriptResult(
        text="Hello world",
        segments=[],
        language="en",
        duration_seconds=60.0,
        provider="assemblyai",
        model="universal-3-pro",
        job_id="j",
    )

    mock_dest = MagicMock()
    mock_dest.upload.side_effect = AuthError("token expired")

    runner = CliRunner()
    with patch("transcriber.cli.load_drive_credentials"):
        with patch("transcriber.cli.AssemblyAIProvider", return_value=mock_provider):
            with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
                result = runner.invoke(
                    app,
                    ["transcribe", str(src), "--budget", "low", "--upload-to-drive", "-y"],
                )

    assert result.exit_code == 4
    assert "token expired" in result.stdout
    # AuthError messages don't include the path; CLI must add the recovery
    # hint so the user knows where to find the .md they just paid for.
    md_files = list(tmp_path.glob("*.md"))
    assert len(md_files) == 1, "Local .md transcript must be preserved on upload failure"
    assert md_files[0].name in result.stdout, "User must see local .md path on upload failure"


def test_transcribe_upload_to_drive_destination_error_exits_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DestinationError after transcribe → exit 4, local .md preserved.

    Exit 4 (post-paid recoverable) rather than exit 2 (config). The
    DestinationError message itself already contains "Transcript saved
    locally at <path>" so the user knows where to recover from.
    """
    from transcriber.providers.base import TranscriptResult

    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "folder-xyz")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda _p, _w: (_p, 60.0))

    mock_provider = MagicMock()
    mock_provider.transcribe.return_value = TranscriptResult(
        text="Hello world",
        segments=[],
        language="en",
        duration_seconds=60.0,
        provider="assemblyai",
        model="universal-3-pro",
        job_id="j",
    )

    mock_dest = MagicMock()
    mock_dest.upload.side_effect = DestinationError(
        "Drive upload failed: 403. Transcript saved locally at /tmp/x.md"
    )

    runner = CliRunner()
    with patch("transcriber.cli.load_drive_credentials"):
        with patch("transcriber.cli.AssemblyAIProvider", return_value=mock_provider):
            with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
                result = runner.invoke(
                    app,
                    ["transcribe", str(src), "--budget", "low", "--upload-to-drive", "-y"],
                )

    assert result.exit_code == 4
    assert "Drive upload failed" in result.stdout
    md_files = list(tmp_path.glob("*.md"))
    assert len(md_files) == 1, "Local .md transcript must be preserved on upload failure"


def test_transcribe_writes_transcript_before_calling_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Architectural invariant: dest.upload() runs only after the .md is on disk.

    The headline guarantee of the upload feature is "transcript-loss-impossible
    by construction". Asserting that ``len(md_files) == 1`` post-failure (the
    other tests do) only proves the file existed at *some* point during the
    test; this asserts the file existed *at the moment upload was invoked*.
    """
    from transcriber.providers.base import TranscriptResult

    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake")
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", "folder-xyz")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda _p, _w: (_p, 60.0))

    mock_provider = MagicMock()
    mock_provider.transcribe.return_value = TranscriptResult(
        text="hello",
        segments=[],
        language="en",
        duration_seconds=60.0,
        provider="assemblyai",
        model="universal-3-pro",
        job_id="j",
    )

    file_existed_at_upload: list[bool] = []

    def _check_then_succeed(path: Path, _name: str) -> str:
        file_existed_at_upload.append(path.exists() and path.stat().st_size > 0)
        return "https://drive.google.com/file/d/x/view"

    mock_dest = MagicMock()
    mock_dest.upload.side_effect = _check_then_succeed

    with patch("transcriber.cli.load_drive_credentials"):
        with patch("transcriber.cli.AssemblyAIProvider", return_value=mock_provider):
            with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
                result = CliRunner().invoke(
                    app,
                    ["transcribe", str(src), "--budget", "low", "--upload-to-drive", "-y"],
                )

    assert result.exit_code == 0, result.output
    assert file_existed_at_upload == [True], (
        "transcript must be on disk (non-empty) when dest.upload() is called"
    )


# ---------------------------------------------------------------------------
# Phase 2 Slice 1 — YouTube captions CLI integration (validation #47-62).
# Tests monkeypatch YouTubeSource.prepare to return a PreparedTranscript
# rather than wiring the library mocks all the way through; library-level
# behaviour is exhaustively covered in tests/unit/test_youtube_source.py.
# ---------------------------------------------------------------------------


def _captions_prepared(
    workspace: object,
    *,
    title: str | None,
    caption_type: str = "manual",
    language: str = "en",
) -> object:
    """Build a PreparedTranscript suitable for CLI captions-path tests."""
    from transcriber.providers.base import Segment, TranscriptResult
    from transcriber.sources.base import PreparedTranscript

    return PreparedTranscript(
        kind="youtube_captions",
        original_uri="https://youtu.be/dQw4w9WgXcQ",
        transcript=TranscriptResult(
            text="hello",
            segments=[Segment(start_ms=0, end_ms=1000, text="hello", speaker=None)],
            language=language,
            duration_seconds=1.0,
            provider="youtube-captions",
            model=None,
            job_id=None,
        ),
        title=title,
        workspace=workspace,  # type: ignore[arg-type]
        extra={"video_id": "dQw4w9WgXcQ", "caption_type": caption_type},
    )


def test_captions_happy_path_skips_provider_and_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation #47: captions URL → PreparedTranscript → output written.
    Budget router NOT called (asserted via a side-effect flag). Provider
    constructor NOT called either."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    from transcriber.sources.youtube import YouTubeSource

    def fake_prepare(uri: str, workspace: object, *, title: str | None = None) -> object:
        return _captions_prepared(workspace, title=title or "Test Title")

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(fake_prepare))

    budget_called = {"yes": False}

    def _track_budget(**_kwargs: object) -> bool:
        budget_called["yes"] = True
        return True

    monkeypatch.setattr("transcriber.cli.budget_check", _track_budget)

    provider_called = {"yes": False}

    class _BoomIfProviderUsed:
        def __init__(self, *_a: object, **_k: object) -> None:
            provider_called["yes"] = True

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _BoomIfProviderUsed)

    result = CliRunner().invoke(
        app, ["transcribe", "https://youtu.be/dQw4w9WgXcQ"]
    )

    assert result.exit_code == 0, result.output
    assert budget_called["yes"] is False, "budget router must NOT fire for captions"
    assert provider_called["yes"] is False, "provider must NOT be constructed"
    # Output filename contains the title (whitespace → dash).
    written = list(tmp_path.glob("Test-Title-*.md"))
    assert len(written) == 1
    assert "source_kind: youtube_captions" in written[0].read_text()


def test_captions_with_budget_free_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation #50: --budget free is OK on captions sources (it's
    $0 — the gate that rejects Drive under free doesn't fire)."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    from transcriber.sources.youtube import YouTubeSource

    monkeypatch.setattr(
        YouTubeSource,
        "prepare",
        staticmethod(lambda uri, ws, *, title=None: _captions_prepared(ws, title="T")),
    )

    result = CliRunner().invoke(
        app, ["transcribe", "https://youtu.be/dQw4w9WgXcQ", "--budget", "free"]
    )
    assert result.exit_code == 0, result.output


# Slice 1's test_captions_no_captions_exits_2_with_documented_message
# was superseded by test_captionless_video_free_budget_emits_budget_aware_message
# below — the no-captions message is now budget-aware and the
# issue-#21 pointer + yt-dlp recipe are gone now that Slice 2 has
# shipped the audio fallback as a real flag rather than a workaround.


def test_captions_ip_blocked_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation #59: IpBlocked → exit 3 (system-level)."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    from youtube_transcript_api import IpBlocked

    from transcriber.sources.youtube import YouTubeSource

    monkeypatch.setattr(
        YouTubeSource,
        "prepare",
        staticmethod(lambda *_a, **_k: (_ for _ in ()).throw(IpBlocked("dQw4w9WgXcQ"))),
    )

    result = CliRunner().invoke(
        app, ["transcribe", "https://youtu.be/dQw4w9WgXcQ"]
    )
    assert result.exit_code == 3
    assert "blocked" in result.output.lower()


def test_captions_language_flag_ignored_with_info_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Validation #51: --language ignored on captions; INFO log mentions
    'ignored' and the actual returned track language."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    from transcriber.sources.youtube import YouTubeSource

    monkeypatch.setattr(
        YouTubeSource,
        "prepare",
        staticmethod(
            lambda uri, ws, *, title=None: _captions_prepared(ws, title="T", language="es")
        ),
    )

    import logging
    with caplog.at_level(logging.INFO, logger="transcriber.cli"):
        result = CliRunner().invoke(
            app, ["transcribe", "https://youtu.be/dQw4w9WgXcQ", "--language", "en"]
        )
    assert result.exit_code == 0, result.output
    assert any(
        "ignored" in rec.getMessage() and "es" in rec.getMessage()
        for rec in caplog.records
    )


def test_captions_no_title_falls_back_to_video_id_stem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Title=None (oembed failed AND no --title) → output filename uses
    the video ID stem. Frontmatter title is also the video ID."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    from transcriber.sources.youtube import YouTubeSource

    monkeypatch.setattr(
        YouTubeSource,
        "prepare",
        staticmethod(lambda uri, ws, *, title=None: _captions_prepared(ws, title=None)),
    )

    result = CliRunner().invoke(
        app, ["transcribe", "https://youtu.be/dQw4w9WgXcQ"]
    )
    assert result.exit_code == 0, result.output
    written = list(tmp_path.glob("dQw4w9WgXcQ-*.md"))
    assert len(written) == 1
    assert "title: dQw4w9WgXcQ" in written[0].read_text()


def test_captions_with_upload_to_drive_uploads_the_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex review finding (PR #31): captions + --upload-to-drive must
    actually upload the .md output. Silently writing locally and
    returning without uploading is a regression — the user explicitly
    asked for upload."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setattr(
        "transcriber.cli.settings.drive_output_folder_id", "folder-xyz"
    )

    from transcriber.sources.youtube import YouTubeSource

    monkeypatch.setattr(
        YouTubeSource,
        "prepare",
        staticmethod(
            lambda uri, ws, *, title=None: _captions_prepared(ws, title="T")
        ),
    )

    mock_dest = MagicMock()
    mock_dest.upload.return_value = "https://drive.google.com/file/d/x/view"

    with patch("transcriber.cli.load_drive_credentials"):
        with patch("transcriber.cli.DriveDestination", return_value=mock_dest):
            result = CliRunner().invoke(
                app,
                [
                    "transcribe",
                    "https://youtu.be/dQw4w9WgXcQ",
                    "--upload-to-drive",
                ],
            )

    assert result.exit_code == 0, result.output
    mock_dest.upload.assert_called_once()
    uploaded_path: Path = mock_dest.upload.call_args.args[0]
    assert uploaded_path.suffix == ".md"
    assert "https://drive.google.com/file/d/x/view" in result.stdout


def test_captions_with_upload_to_drive_no_folder_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-flight folder check fires for captions too — same fail-fast
    invariant as the Drive/local path. Without this, a user without a
    folder configured would get the captions transcript locally but a
    cryptic post-fact upload error."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setattr("transcriber.cli.settings.drive_output_folder_id", None)

    result = CliRunner().invoke(
        app,
        ["transcribe", "https://youtu.be/dQw4w9WgXcQ", "--upload-to-drive"],
    )
    assert result.exit_code == 2
    assert "No Drive folder configured" in result.output


# ---------------------------------------------------------------------------
# YouTube exception → exit code matrix (PR #31 test-analyzer Critical 1).
# Validation cases #53–#62: each library exception subclass must route
# through _handle_youtube_exception to the documented exit code AND
# message phrase. Without these tests a branch-order regression in
# _handle_youtube_exception (e.g., AgeRestricted moved below
# VideoUnavailable) ships silently.
# ---------------------------------------------------------------------------


def _make_yt_exception(name: str) -> Exception:
    """Build a library exception with the right constructor signature.
    Constructors differ — VideoUnplayable needs 3 args, YouTubeRequestFailed
    needs an HTTPError, NoTranscriptFound takes a TranscriptList. We use
    minimal stand-ins."""
    from unittest.mock import MagicMock

    import requests as _requests
    import youtube_transcript_api as y

    video_id = "dQw4w9WgXcQ"
    if name == "VideoUnplayable":
        return y.VideoUnplayable(video_id, "test reason", [])
    if name == "NoTranscriptFound":
        return y.NoTranscriptFound(video_id, ["en"], MagicMock())
    if name == "YouTubeRequestFailed":
        http_err = _requests.exceptions.HTTPError("503 transient")
        return y.YouTubeRequestFailed(video_id, http_err)
    cls = getattr(y, name)
    return cls(video_id)


@pytest.mark.parametrize(
    "exception_name, expected_exit, expected_substring",
    [
        # Slice 2 removed TranscriptsDisabled + NoTranscriptFound from
        # this parametrize — those now surface as NoCaptionsAvailable
        # from prepare() and route through the budget-aware audio-fallback
        # path. Covered by test_captionless_video_*_budget_* tests below.
        ("VideoUnavailable", 2, "Video unavailable"),
        ("VideoUnplayable", 2, "Video unplayable"),
        ("InvalidVideoId", 2, "rejected the video ID"),
        ("AgeRestricted", 2, "age-restricted"),
        ("PoTokenRequired", 2, "PO-token"),
        ("IpBlocked", 3, "blocked the request"),
        ("RequestBlocked", 3, "blocked the request"),
        ("YouTubeRequestFailed", 3, "transient YouTube response"),
        ("FailedToCreateConsentCookie", 3, "consent flow"),
        ("YouTubeDataUnparsable", 3, "Unexpected error"),
    ],
)
def test_captions_library_exception_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception_name: str,
    expected_exit: int,
    expected_substring: str,
) -> None:
    """Every library exception this CLI catches must route to the
    spec-documented exit code with a user-facing message that contains
    the documented diagnostic phrase. Branch-order or whitelist-typo
    regressions break this test, not just user expectations."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    from transcriber.sources.youtube import YouTubeSource

    exc = _make_yt_exception(exception_name)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise exc

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(boom))

    result = CliRunner().invoke(
        app, ["transcribe", "https://youtu.be/dQw4w9WgXcQ"]
    )

    assert result.exit_code == expected_exit, (
        f"{exception_name} expected exit {expected_exit}, "
        f"got {result.exit_code}: {result.output}"
    )
    assert expected_substring in result.output, (
        f"{exception_name}: expected {expected_substring!r} in output, "
        f"got {result.output!r}"
    )


# ---------------------------------------------------------------------------
# Phase 2 Slice 2 — NoCaptionsAvailable routing + audio-fallback flow.
# Free budget → exit 2 with budget-aware message; low+ budget → probe,
# budget gate with real cost estimate, download. Tests in this block
# stub YouTubeSource.{prepare, probe_audio, download_audio} directly so
# we don't depend on yt-dlp at test time.
# ---------------------------------------------------------------------------


def test_captionless_video_free_budget_emits_budget_aware_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default free budget + no captions → exit 2 with a message that
    points the user at ``--budget low`` for audio fallback. No probe
    attempted (the pre-flight short-circuit the spec promises in
    §"User-visible behaviour matrix")."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    from transcriber.sources.youtube import (
        NoCaptionsAvailable,
        YouTubeSource,
    )

    probe_calls = {"n": 0}

    def fake_probe(*_args: object, **_kwargs: object) -> None:
        probe_calls["n"] += 1

    def boom(*_args: object, **_kwargs: object) -> None:
        raise NoCaptionsAvailable("no captions for test")

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(boom))
    monkeypatch.setattr(
        YouTubeSource, "probe_audio", staticmethod(fake_probe)
    )

    result = CliRunner().invoke(
        app, ["transcribe", "https://youtu.be/dQw4w9WgXcQ"]
    )

    assert result.exit_code == 2, result.output
    assert "--budget low" in result.output
    assert "audio fallback" in result.output
    assert probe_calls["n"] == 0, "free budget must short-circuit before probe"


def test_captionless_video_low_budget_declines_at_prompt_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Low budget + no captions → probe fires → cost prompt shown → user
    types 'n' → exit 0, no download attempted (cancelled cleanly with
    'no charge incurred' messaging)."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")

    from transcriber.sources.youtube import (
        AudioProbe,
        NoCaptionsAvailable,
        YouTubeSource,
    )

    def boom(*_args: object, **_kwargs: object) -> None:
        raise NoCaptionsAvailable("no captions for test")

    def fake_probe(_uri: str) -> AudioProbe:
        return AudioProbe(duration=300, title="Test Video")

    download_calls = {"n": 0}

    def fake_download(*_args: object, **_kwargs: object) -> None:
        download_calls["n"] += 1

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(boom))
    monkeypatch.setattr(
        YouTubeSource, "probe_audio", staticmethod(fake_probe)
    )
    monkeypatch.setattr(
        YouTubeSource, "download_audio", staticmethod(fake_download)
    )
    # User types "n" at the budget prompt.
    monkeypatch.setattr(
        "transcriber.cli._confirm_or_decline", lambda _msg: False
    )

    result = CliRunner().invoke(
        app,
        ["transcribe", "https://youtu.be/dQw4w9WgXcQ", "--budget", "low"],
    )

    assert result.exit_code == 0, result.output
    assert "Cancelled" in result.output
    assert "no charge" in result.output
    assert download_calls["n"] == 0, "decline must skip download"


def _make_yt_dlp_exception(name: str, message: str = "test") -> Exception:
    """Construct a yt-dlp exception by class name with the right
    constructor signature. Mirrors test_youtube_source.py's
    _build_yt_exception helper but for yt-dlp instead of the captions
    library."""
    if name == "OSError":
        return OSError(message)
    from transcriber.sources.youtube import ProbeDurationUnknown

    if name == "ProbeDurationUnknown":
        return ProbeDurationUnknown("https://youtu.be/dQw4w9WgXcQ")

    import yt_dlp.utils as ydl_utils

    cls = getattr(ydl_utils, name)
    if name == "ExtractorError":
        return cls(message)
    if name == "GeoRestrictedError":
        return cls(message, countries=["US"])
    if name == "UnavailableVideoError":
        return cls(message)
    if name == "UnsupportedError":
        return cls(message)
    return cls(message)


@pytest.mark.parametrize(
    "exc_name, exc_message, raise_at, expected_exit, expected_substring",
    [
        # Exit-2 family: video-level user errors yt-dlp can't help with.
        ("UnavailableVideoError", "test gone", "probe", 2, "unavailable for download"),
        ("UnsupportedError", "test", "probe", 2, "not supported by yt-dlp"),
        ("GeoRestrictedError", "test", "probe", 2, "geo-restricted"),
        ("ExtractorError", "age-restricted: members only", "probe", 2, "requires authentication"),
        ("ExtractorError", "some other extractor failure", "probe", 2, "audio extraction failed"),
        ("ProbeDurationUnknown", "", "probe", 2, "could not determine video duration"),
        # Exit-3 family: network exhaustion after retries.
        ("DownloadError", "network failure after retries", "download", 3, "network failure"),
        ("DownloadError", "generic download failure", "download", 3, "audio download failed"),
        # Exit-4 family: local I/O.
        ("PostProcessingError", "ffmpeg crashed", "download", 4, "ffmpeg failed"),
        ("OSError", "disk full", "download", 4, "local I/O error"),
    ],
)
def test_yt_dlp_exception_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc_name: str,
    exc_message: str,
    raise_at: str,
    expected_exit: int,
    expected_substring: str,
) -> None:
    """Every yt-dlp exception this CLI may catch maps to the spec
    exit-code matrix (plan.md §4c). Branch-order or whitelist-typo
    regressions break this test — particularly important for the
    subclass-ordered branches (GeoRestrictedError before ExtractorError,
    UnavailableVideoError before ExtractorError)."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")

    from transcriber.sources.youtube import (
        AudioProbe,
        NoCaptionsAvailable,
        YouTubeSource,
    )

    def captions_boom(*_a: object, **_k: object) -> None:
        raise NoCaptionsAvailable("no captions for test")

    exc = _make_yt_dlp_exception(exc_name, exc_message)

    def maybe_probe_boom(_uri: str) -> AudioProbe:
        if raise_at == "probe":
            raise exc
        return AudioProbe(duration=300, title="t")

    def maybe_download_boom(*_a: object, **_k: object) -> None:
        if raise_at == "download":
            raise exc

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(captions_boom))
    monkeypatch.setattr(YouTubeSource, "probe_audio", staticmethod(maybe_probe_boom))
    monkeypatch.setattr(
        YouTubeSource, "download_audio", staticmethod(maybe_download_boom)
    )

    result = CliRunner().invoke(
        app,
        [
            "transcribe",
            "https://youtu.be/dQw4w9WgXcQ",
            "--budget",
            "low",
            "-y",
        ],
    )

    assert result.exit_code == expected_exit, (
        f"{exc_name}({exc_message!r}) at {raise_at}: "
        f"expected exit {expected_exit}, got {result.exit_code}: {result.output}"
    )
    # Case-insensitive substring — test substrings are written
    # presentationally (lowercase), production messages use Title Case
    # for first words. We care about the words being present, not the
    # specific casing — that's a UX-polish decision the spec doesn't
    # pin and the test shouldn't either.
    assert expected_substring.lower() in result.output.lower(), (
        f"{exc_name}({exc_message!r}): expected {expected_substring!r}, "
        f"got: {result.output}"
    )


def test_captionless_low_budget_shows_dollar_estimate_and_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex P2: the original implementation passed ``cost_summary`` to
    budget_check, which suppresses the duration-derived ``$X.XX``
    estimate AND the soft-cap warning. The user was being asked to
    authorise a paid call without seeing the actual cost. Verify the
    new flow: emit the audio-fallback context via notify(); let
    budget_check render the real estimate + soft-cap warning.

    The audio-fallback decline path is the cheapest place to assert
    the output: probe runs, prompt would fire, decline cancels — all
    the budget_check output is captured."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")

    from transcriber.sources.youtube import (
        AudioProbe,
        NoCaptionsAvailable,
        YouTubeSource,
    )

    def captions_boom(*_a: object, **_k: object) -> None:
        raise NoCaptionsAvailable("no captions")

    # 600 seconds = 10 min → ~$0.10 at AssemblyAI's universal-3 rate
    # (~$0.65/hr after the PR #18 rate-correction). Doesn't matter for
    # the substring check; we only care that *some* dollar amount and
    # the context line appear.
    def fake_probe(_uri: str) -> AudioProbe:
        return AudioProbe(duration=600, title="t")

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(captions_boom))
    monkeypatch.setattr(YouTubeSource, "probe_audio", staticmethod(fake_probe))
    monkeypatch.setattr(
        "transcriber.cli._confirm_or_decline", lambda _msg: False
    )

    result = CliRunner().invoke(
        app,
        ["transcribe", "https://youtu.be/dQw4w9WgXcQ", "--budget", "low"],
    )

    assert result.exit_code == 0, result.output
    # The audio-fallback context line is now emitted via notify() so
    # the user knows WHY the prompt is firing.
    collapsed = " ".join(result.output.split())
    assert "audio fallback" in collapsed.lower()
    # And budget_check's own estimate line fires too, showing the
    # actual dollar amount.
    assert "Estimated cost" in result.output
    assert "$" in result.output


def test_captionless_video_explicit_title_overrides_probe_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex P2: --title is documented as 'Frontmatter + filename
    stem' (per the CLI help). The audio-fallback path was passing the
    probe title into PreparedMedia.title unconditionally, so the
    frontmatter + H1 always showed the probe title even when the user
    supplied --title. Filename used --title (correct) but the rendered
    content used probe title (wrong). Verify both surfaces honour
    --title."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")

    from transcriber.core.workspace import RunWorkspace
    from transcriber.providers.base import Segment, TranscriptResult
    from transcriber.sources.base import PreparedMedia
    from transcriber.sources.youtube import (
        AudioProbe,
        NoCaptionsAvailable,
        YouTubeSource,
    )

    workspace = RunWorkspace()
    audio = workspace.path("audio.m4a")
    audio.write_bytes(b"")

    def captions_boom(*_a: object, **_k: object) -> None:
        raise NoCaptionsAvailable("no captions")

    def fake_probe(_uri: str) -> AudioProbe:
        return AudioProbe(duration=300, title="Probe Title")

    captured: dict[str, str | None] = {"download_title_kwarg": None}

    def fake_download(
        _u: str,
        ws: RunWorkspace,
        p: AudioProbe,
        *,
        title: str | None = None,
    ) -> PreparedMedia:
        captured["download_title_kwarg"] = title
        return PreparedMedia(
            kind="youtube_audio",
            original_uri="https://youtu.be/dQw4w9WgXcQ",
            local_path=audio,
            title=title if title is not None else p.title,
            duration_seconds=float(p.duration),
            workspace=ws,
            extra={"video_id": "dQw4w9WgXcQ", "probe_duration": str(p.duration)},
            remote_url=None,
        )

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(captions_boom))
    monkeypatch.setattr(YouTubeSource, "probe_audio", staticmethod(fake_probe))
    monkeypatch.setattr(YouTubeSource, "download_audio", staticmethod(fake_download))
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda p, _w: (p, 300.0))

    class _OkProvider:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def transcribe(self, *_a: object, **_k: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=300.0,
                provider="assemblyai",
                model="universal-3-pro",
                job_id="j",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    result = CliRunner().invoke(
        app,
        [
            "transcribe",
            "https://youtu.be/dQw4w9WgXcQ",
            "--budget", "low", "-y",
            "--title", "Custom Title",
        ],
    )

    assert result.exit_code == 0, result.output
    # --title flows into download_audio as a keyword arg so the
    # source assigns it to PreparedMedia.title.
    assert captured["download_title_kwarg"] == "Custom Title", (
        f"download_audio received title={captured['download_title_kwarg']!r}; "
        f"expected 'Custom Title'"
    )
    # Frontmatter + H1 use the --title value, NOT the probe title.
    output_files = list(tmp_path.glob("*.md"))
    assert len(output_files) == 1
    content = output_files[0].read_text()
    assert "title: Custom Title" in content
    assert "# Custom Title" in content
    assert "Probe Title" not in content


def test_captionless_low_budget_fires_exactly_one_budget_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §4e + Codex Important #2 regression: the audio-fallback path's
    pre-download budget_check must NOT be re-fired by the existing
    local-file pipeline's post-extract budget_check (otherwise the user
    sees two prompts for one transcription). Counts the number of times
    the prompt callback is invoked; exactly one is required."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")

    from transcriber.core.workspace import RunWorkspace
    from transcriber.providers.base import Segment, TranscriptResult
    from transcriber.sources.base import PreparedMedia
    from transcriber.sources.youtube import (
        AudioProbe,
        NoCaptionsAvailable,
        YouTubeSource,
    )

    workspace = RunWorkspace()
    audio = workspace.path("audio.m4a")
    audio.write_bytes(b"")

    def captions_boom(*_a: object, **_k: object) -> None:
        raise NoCaptionsAvailable("no captions")

    def fake_probe(_uri: str) -> AudioProbe:
        return AudioProbe(duration=300, title="Test Video")

    def fake_download(
        _u: str,
        ws: RunWorkspace,
        p: AudioProbe,
        *,
        title: str | None = None,
    ) -> PreparedMedia:
        return PreparedMedia(
            kind="youtube_audio",
            original_uri="https://youtu.be/dQw4w9WgXcQ",
            local_path=audio,
            title=p.title,
            duration_seconds=float(p.duration),
            workspace=ws,
            extra={"video_id": "dQw4w9WgXcQ", "probe_duration": str(p.duration)},
            remote_url=None,
        )

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(captions_boom))
    monkeypatch.setattr(YouTubeSource, "probe_audio", staticmethod(fake_probe))
    monkeypatch.setattr(YouTubeSource, "download_audio", staticmethod(fake_download))
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda p, _w: (p, 300.0))

    prompt_calls = {"n": 0}

    def counting_prompt(_msg: str) -> bool:
        prompt_calls["n"] += 1
        return True  # always confirm

    monkeypatch.setattr("transcriber.cli._confirm_or_decline", counting_prompt)

    class _OkProvider:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def transcribe(self, *_a: object, **_k: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=300.0,
                provider="assemblyai",
                model="universal-3-pro",
                job_id="j",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    result = CliRunner().invoke(
        app,
        ["transcribe", "https://youtu.be/dQw4w9WgXcQ", "--budget", "low"],
    )

    assert result.exit_code == 0, result.output
    assert prompt_calls["n"] == 1, (
        f"expected exactly one budget prompt for the audio-fallback "
        f"flow, got {prompt_calls['n']}: {result.output}"
    )


def test_local_file_budget_prompt_unchanged_by_slice_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Slice 1 regression: kind=local still fires exactly one budget
    prompt after extract_audio. The §4e bypass must only short-circuit
    for kind=youtube_audio, not for any other PreparedMedia kind."""
    src = tmp_path / "x.wav"
    src.write_bytes(b"")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda p, _w: (p, 60.0))

    from transcriber.providers.base import Segment, TranscriptResult

    prompt_calls = {"n": 0}

    def counting_prompt(_msg: str) -> bool:
        prompt_calls["n"] += 1
        return True

    monkeypatch.setattr("transcriber.cli._confirm_or_decline", counting_prompt)

    class _OkProvider:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def transcribe(self, *_a: object, **_k: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=60.0,
                provider="assemblyai",
                model="universal-3-pro",
                job_id="j",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    result = CliRunner().invoke(
        app, ["transcribe", str(src), "--budget", "low"]
    )

    assert result.exit_code == 0, result.output
    assert prompt_calls["n"] == 1, (
        f"local-file path must fire exactly one prompt; "
        f"got {prompt_calls['n']}"
    )


def test_captionless_empty_probe_title_falls_back_to_video_id_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence-in-depth: if the yt-dlp probe returns no title (rare,
    but possible — _probe_metadata coerces missing/None to ``""``), the
    filename falls back to the video_id stem rather than producing an
    output named like ``-2026-05-13.md`` (leading dash). Mirrors the
    captions-arm fallback at the same call site (review finding I4:
    loud over silent — fall back to the video ID, not 'untitled')."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")

    from transcriber.core.workspace import RunWorkspace
    from transcriber.providers.base import Segment, TranscriptResult
    from transcriber.sources.base import PreparedMedia
    from transcriber.sources.youtube import (
        AudioProbe,
        NoCaptionsAvailable,
        YouTubeSource,
    )

    workspace = RunWorkspace()
    audio = workspace.path("audio.m4a")
    audio.write_bytes(b"")

    def captions_boom(*_a: object, **_k: object) -> None:
        raise NoCaptionsAvailable("no captions")

    def fake_probe(_uri: str) -> AudioProbe:
        return AudioProbe(duration=300, title="")  # empty title!

    def fake_download(
        _u: str,
        ws: RunWorkspace,
        p: AudioProbe,
        *,
        title: str | None = None,
    ) -> PreparedMedia:
        return PreparedMedia(
            kind="youtube_audio",
            original_uri="https://youtu.be/dQw4w9WgXcQ",
            local_path=audio,
            title=p.title,  # ""
            duration_seconds=float(p.duration),
            workspace=ws,
            extra={"video_id": "dQw4w9WgXcQ", "probe_duration": str(p.duration)},
            remote_url=None,
        )

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(captions_boom))
    monkeypatch.setattr(YouTubeSource, "probe_audio", staticmethod(fake_probe))
    monkeypatch.setattr(YouTubeSource, "download_audio", staticmethod(fake_download))
    monkeypatch.setattr("transcriber.cli.extract_audio", lambda p, _w: (p, 300.0))

    class _OkProvider:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def transcribe(self, *_a: object, **_k: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=300.0,
                provider="assemblyai",
                model="universal-3-pro",
                job_id="j",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    result = CliRunner().invoke(
        app,
        ["transcribe", "https://youtu.be/dQw4w9WgXcQ", "--budget", "low", "-y"],
    )

    assert result.exit_code == 0, result.output
    output_files = list(tmp_path.glob("*.md"))
    assert len(output_files) == 1
    # Falls back to video_id stem, NOT a leading-dash filename.
    assert output_files[0].name.startswith("dQw4w9WgXcQ-"), output_files[0].name


@pytest.mark.parametrize(
    "inner_name, inner_message, expected_exit, expected_substring",
    [
        ("GeoRestrictedError", "blocked in your region", 2, "geo-restricted"),
        ("UnavailableVideoError", "Private video", 2, "unavailable for download"),
        ("UnsupportedError", "no extractor", 2, "not supported by yt-dlp"),
        ("ExtractorError", "Sign in to confirm your age", 2, "requires authentication"),
        ("ExtractorError", "something else", 2, "audio extraction failed"),
    ],
)
def test_yt_dlp_exception_matrix_unwraps_download_error_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    inner_name: str,
    inner_message: str,
    expected_exit: int,
    expected_substring: str,
) -> None:
    """Codex P2: yt-dlp's ``YoutubeDL.extract_info`` routes many
    extractor failures through ``report_error()``, which raises
    ``DownloadError`` with the original ``ExtractorError``-family
    exception in ``__cause__``. Without unwrapping, our matrix would
    classify those as exit 3 network failures instead of the
    user-actionable exit 2 cases.

    Verify that wrapped causes get the right exit code based on the
    inner exception, not the outer DownloadError class."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")

    from yt_dlp.utils import DownloadError

    from transcriber.sources.youtube import (
        AudioProbe,
        NoCaptionsAvailable,
        YouTubeSource,
    )

    def captions_boom(*_a: object, **_k: object) -> None:
        raise NoCaptionsAvailable("no captions")

    inner_exc = _make_yt_dlp_exception(inner_name, inner_message)
    outer_exc = DownloadError("yt-dlp report_error wrapped this")
    outer_exc.__cause__ = inner_exc

    def probe_boom(_uri: str) -> AudioProbe:
        raise outer_exc

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(captions_boom))
    monkeypatch.setattr(YouTubeSource, "probe_audio", staticmethod(probe_boom))

    result = CliRunner().invoke(
        app,
        ["transcribe", "https://youtu.be/dQw4w9WgXcQ", "--budget", "low", "-y"],
    )

    assert result.exit_code == expected_exit, (
        f"DownloadError(__cause__={inner_name}): "
        f"expected exit {expected_exit}, got {result.exit_code}: {result.output}"
    )
    assert expected_substring.lower() in result.output.lower(), (
        f"DownloadError(__cause__={inner_name}({inner_message!r})): "
        f"expected {expected_substring!r}; got: {result.output}"
    )


def test_yt_dlp_download_failure_calls_out_no_charge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec edge case: probe succeeds and user authorises spend, but the
    download then fails. The error message must include 'no charge'
    messaging so the user knows their AssemblyAI bill wasn't touched."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")

    from yt_dlp.utils import DownloadError

    from transcriber.sources.youtube import (
        AudioProbe,
        NoCaptionsAvailable,
        YouTubeSource,
    )

    def captions_boom(*_a: object, **_k: object) -> None:
        raise NoCaptionsAvailable("no captions")

    def fake_probe(_uri: str) -> AudioProbe:
        return AudioProbe(duration=300, title="t")

    def download_boom(*_a: object, **_k: object) -> None:
        raise DownloadError("connection reset mid-stream")

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(captions_boom))
    monkeypatch.setattr(YouTubeSource, "probe_audio", staticmethod(fake_probe))
    monkeypatch.setattr(YouTubeSource, "download_audio", staticmethod(download_boom))

    result = CliRunner().invoke(
        app,
        ["transcribe", "https://youtu.be/dQw4w9WgXcQ", "--budget", "low", "-y"],
    )

    assert result.exit_code == 3
    # The message contains "(no AssemblyAI charge incurred)". Rich wraps
    # long lines in the captured output, so "charge incurred" may span
    # a newline. Collapse whitespace before the substring check.
    collapsed = " ".join(result.output.lower().split())
    assert "charge incurred" in collapsed


def test_captionless_video_low_budget_yes_flag_runs_full_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Low budget + ``-y`` + no captions → probe → budget gate passes
    silently → download → existing pipeline (extract_audio, AssemblyAI,
    write). Exit 0, output written.

    This is the happy path for captionless videos. After Phase B4 lands
    the kind=youtube_audio bypass for the existing pipeline's second
    budget_check, this test should still pass byte-identically — the
    -y flag silences both gates today; B4 just removes the redundant
    gate."""
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")

    from transcriber.core.workspace import RunWorkspace
    from transcriber.providers.base import Segment, TranscriptResult
    from transcriber.sources.base import PreparedMedia
    from transcriber.sources.youtube import (
        AudioProbe,
        NoCaptionsAvailable,
        YouTubeSource,
    )

    workspace = RunWorkspace()
    downloaded_audio = workspace.path("audio.m4a")
    downloaded_audio.write_bytes(b"")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise NoCaptionsAvailable("no captions for test")

    def fake_probe(_uri: str) -> AudioProbe:
        return AudioProbe(duration=300, title="Test Video")

    def fake_download(
        _uri: str,
        ws: RunWorkspace,
        probe: AudioProbe,
        *,
        title: str | None = None,
    ) -> PreparedMedia:
        return PreparedMedia(
            kind="youtube_audio",
            original_uri="https://youtu.be/dQw4w9WgXcQ",
            local_path=downloaded_audio,
            title=probe.title,
            duration_seconds=float(probe.duration),
            workspace=ws,
            extra={
                "video_id": "dQw4w9WgXcQ",
                "probe_duration": str(probe.duration),
            },
            remote_url=None,
        )

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(boom))
    monkeypatch.setattr(
        YouTubeSource, "probe_audio", staticmethod(fake_probe)
    )
    monkeypatch.setattr(
        YouTubeSource, "download_audio", staticmethod(fake_download)
    )
    monkeypatch.setattr(
        "transcriber.cli.extract_audio",
        lambda path, _ws: (path, 300.0),
    )

    class _OkProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(
            self, *_args: object, **_kwargs: object
        ) -> TranscriptResult:
            return TranscriptResult(
                text="hello",
                segments=[
                    Segment(
                        start_ms=0, end_ms=1000, text="hello", speaker=None
                    )
                ],
                language="en",
                duration_seconds=300.0,
                provider="assemblyai",
                model="universal-3-pro",
                job_id="job-abc",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    result = CliRunner().invoke(
        app,
        [
            "transcribe",
            "https://youtu.be/dQw4w9WgXcQ",
            "--budget",
            "low",
            "-y",
        ],
    )

    assert result.exit_code == 0, result.output
    # Output file exists with the probe-derived title (slugified by atomic.write).
    output_files = list(tmp_path.glob("*.md"))
    assert len(output_files) == 1, list(tmp_path.iterdir())
    assert "Test-Video" in output_files[0].name or "Test_Video" in output_files[0].name



def test_captions_network_exhaustion_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation #62 + PR #31 test-analyzer Critical 2: when tenacity
    retries exhaust on the captions fetch, a ``requests.RequestException``
    escapes ``YouTubeSource.prepare``. The CLI must catch it via the
    broad ``requests.RequestException`` clause and exit 3 with the
    documented ``Network error fetching captions`` message — never a
    raw traceback."""
    import requests as _requests

    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    from transcriber.sources.youtube import YouTubeSource

    def network_fail(*_args: object, **_kwargs: object) -> None:
        raise _requests.Timeout("retries exhausted")

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(network_fail))

    result = CliRunner().invoke(
        app, ["transcribe", "https://youtu.be/dQw4w9WgXcQ"]
    )
    assert result.exit_code == 3
    assert "Network error fetching captions" in result.output


def test_captions_chunked_encoding_at_cli_layer_exits_3_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for the silent-failure-hunter Critical finding:
    a ``ChunkedEncodingError`` (which is NOT a Timeout/ConnectionError
    subclass but IS a RequestException) must produce a clean exit 3,
    not a raw traceback. Locks the widened CLI catch."""
    import requests as _requests

    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    from transcriber.sources.youtube import YouTubeSource

    def chunked(*_args: object, **_kwargs: object) -> None:
        raise _requests.exceptions.ChunkedEncodingError("connection cut")

    monkeypatch.setattr(YouTubeSource, "prepare", staticmethod(chunked))

    result = CliRunner().invoke(
        app, ["transcribe", "https://youtu.be/dQw4w9WgXcQ"]
    )
    assert result.exit_code == 3
    assert "Network error fetching captions" in result.output
