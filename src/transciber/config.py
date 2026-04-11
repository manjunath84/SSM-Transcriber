"""Transciber configuration — pydantic-settings singleton.

All internal settings are prefixed ``TRANSCIBER_``. Third-party API keys
(DEEPGRAM_API_KEY, OPENAI_API_KEY, etc.) are read directly by vendor SDKs
and are not managed here.

Phase 0.5: stub with only the fields needed for the CLI to start.
Phase 1+ will extend this with cache, output, and provider settings as
each module is implemented.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TranscriberSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRANSCIBER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Transcription ────────────────────────────────────────────────────────
    whisper_model_size: str = "base"
    whisper_device: str = "auto"
    transcription_provider: str = "faster_whisper"
    default_budget: str = "free"

    # ── Paths ────────────────────────────────────────────────────────────────
    output_dir: Path = Path("./output")
    cache_dir: Path = Path("~/.cache/transciber")
    cache_enabled: bool = True

    # ── LLM (Phase 6a+) ──────────────────────────────────────────────────────
    llm_model: str = "groq/llama-3.1-8b-instant"

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    @field_validator("output_dir", "cache_dir", mode="after")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        """Expand `~` in path settings sourced from env or .env files."""
        return Path(value).expanduser()


settings = TranscriberSettings()
