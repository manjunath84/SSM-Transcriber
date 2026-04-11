"""Phase 0 smoke tests — prove the package imports and CLI is wired."""

from __future__ import annotations

from typer.testing import CliRunner

from transciber import __version__
from transciber.cli import app
from transciber.config import settings


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
    runner = CliRunner()
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    assert "faster_whisper" in result.stdout
    assert "$0.000" in result.stdout


def test_cli_config_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "TRANSCIBER_WHISPER_MODEL_SIZE" in result.stdout
