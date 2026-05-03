"""CLI integration tests — exit-code matrix.

Covers case 23 (exit codes for each error path) with subsystems mocked
where needed. Case 24 (filename collision suffix-increment) is verified
via the unit tests for ``core/atomic.resolve_collision``; the CLI just
calls that function with the planned output path.
"""

from __future__ import annotations

from pathlib import Path

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
