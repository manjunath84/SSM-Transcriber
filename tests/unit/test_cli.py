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
