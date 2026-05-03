"""Phase 0 smoke tests — prove the package imports and CLI is wired."""

from __future__ import annotations

from typer.testing import CliRunner

from transcriber import __version__
from transcriber.cli import app
from transcriber.config import settings


def test_version_is_set() -> None:
    assert __version__ == "0.1.0"


def test_settings_load_with_defaults() -> None:
    assert settings.whisper_model_size == "base"
    assert settings.transcription_provider == "faster_whisper"
    assert settings.default_budget == "free"
    assert settings.cache_enabled is True


def test_cli_help_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "transcribe" in result.stdout
    assert "providers" in result.stdout
    assert "config" in result.stdout


def test_cli_providers_command() -> None:
    """Slice 1 only ships AssemblyAI; faster-whisper returns when Phase 1 MVP lands."""
    runner = CliRunner()
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    assert "assemblyai" in result.stdout
    assert "$0.009" in result.stdout


def test_cli_config_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "TRANSCRIBER_WHISPER_MODEL_SIZE" in result.stdout


def test_cli_transcribe_missing_file_exits_4() -> None:
    """Slice 1 contract: a non-existent source path is a local error → exit 4."""
    runner = CliRunner()
    result = runner.invoke(app, ["transcribe", "./does-not-exist.mp4", "--budget", "low", "-y"])
    assert result.exit_code == 4
    assert "not found" in result.stdout.lower()


def test_cli_auth_stub_exits_nonzero() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "google-drive"])
    assert result.exit_code == 1


def test_cache_dir_expands_tilde(monkeypatch: object) -> None:
    """TRANSCRIBER_CACHE_DIR with ~ must be expanded to an absolute path."""
    import os

    from transcriber.config import TranscriberSettings

    os.environ["TRANSCRIBER_CACHE_DIR"] = "~/.cache/transcriber-test"
    try:
        s = TranscriberSettings()
        assert not str(s.cache_dir).startswith("~")
        assert str(s.cache_dir).startswith("/")
    finally:
        del os.environ["TRANSCRIBER_CACHE_DIR"]
