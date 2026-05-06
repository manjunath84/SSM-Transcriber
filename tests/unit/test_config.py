"""Tests for ``transcriber.config`` — settings singleton + .env-loading boundary.

The most load-bearing test here is ``test_dotenv_unprefixed_key_visible``: it
locks in the fix from commit ``d5eb072``. Without ``load_dotenv()`` at config
import, ``ASSEMBLYAI_API_KEY`` in ``.env`` would be invisible to ``os.getenv``
(``pydantic-settings`` only loads declared ``TRANSCRIBER_*`` fields). The
unit-test suite previously bypassed this entirely by setting the env var via
``monkeypatch.setenv`` — that defect class is exactly what the manual real-API
runbook caught and is now covered here.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_assemblyai_configured_true_for_normal_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "real-looking-key-123")
    from transcriber.config import settings

    assert settings.assemblyai_configured is True


def test_assemblyai_configured_false_for_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)
    from transcriber.config import settings

    assert settings.assemblyai_configured is False


def test_assemblyai_configured_false_for_whitespace_only_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without stripping, ``"   "`` would pass Gate 1 then 401 on the actual
    AssemblyAI call — only after the user has waited for ffmpeg + confirmed
    cost. Strip + truthy check prevents that wasted round trip."""
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "   ")
    from transcriber.config import settings

    assert settings.assemblyai_configured is False


def test_assemblyai_configured_false_for_empty_string_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "")
    from transcriber.config import settings

    assert settings.assemblyai_configured is False


def test_dotenv_unprefixed_key_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for the PR #12 incident: an unprefixed vendor key in `.env`
    must reach ``os.getenv`` after config module import. Without the
    ``load_dotenv()`` call at the top of ``config.py``, ``pydantic-settings``
    would skip this key entirely (it only reads ``TRANSCRIBER_*`` fields).
    """
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "ASSEMBLYAI_API_KEY=key-from-dotenv-file\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    # Force re-import so load_dotenv() runs against the new working dir.
    import transcriber.config

    importlib.reload(transcriber.config)

    assert transcriber.config.settings.assemblyai_configured is True


def test_redacted_dump_excludes_unknown_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """If a future contributor adds a secret-bearing field to the model
    without listing it in the allowlist, ``redacted_dump`` must drop it
    rather than silently leak it via the CLI ``config`` command."""
    from transcriber.config import settings

    dump = settings.redacted_dump()
    # All keys in the dump are members of the explicit allowlist.
    expected = {
        "whisper_model_size",
        "whisper_device",
        "transcription_provider",
        "default_budget",
        "output_dir",
        "cache_dir",
        "cache_enabled",
        "keep_temp",
        "llm_model",
        "drive_output_folder_id",
        "log_level",
    }
    assert set(dump.keys()).issubset(expected)
