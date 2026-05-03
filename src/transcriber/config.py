"""Transcriber configuration — pydantic-settings singleton.

All internal settings are prefixed ``TRANSCRIBER_``. Third-party API keys
(``ASSEMBLYAI_API_KEY``, ``DEEPGRAM_API_KEY``, ``OPENAI_API_KEY``, etc.) are
unprefixed by convention and read via ``os.getenv`` from the process
environment. ``pydantic-settings`` only loads ``.env`` values for declared
model fields (i.e. the ``TRANSCRIBER_*`` ones), so we eagerly call
``load_dotenv`` at module import to push every ``.env`` entry — including
unprefixed vendor keys — into ``os.environ`` before the singleton is built.
The ``assemblyai_configured`` boundary helper keeps the only ``os.getenv``
call for the vendor key inside this module, so the rest of the codebase
can honour the "never read os.environ directly" rule from CLAUDE.md.

Phase 0.5: stub with only the fields needed for the CLI to start.
Phase 1+ will extend this with cache, output, and provider settings as
each module is implemented.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load `.env` into `os.environ` for unprefixed vendor keys (ASSEMBLYAI_API_KEY,
# etc.). `pydantic-settings` reads `.env` for declared TRANSCRIBER_* fields
# only, so this is the boundary where vendor keys actually become visible to
# `os.getenv`. `override=False` means real env vars win over the file.
load_dotenv(override=False)


class TranscriberSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRANSCRIBER_",
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
    cache_dir: Path = Path("~/.cache/transcriber")
    cache_enabled: bool = True
    keep_temp: bool = False

    # ── LLM (Phase 6a+) ──────────────────────────────────────────────────────
    llm_model: str = "groq/llama-3.1-8b-instant"

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    @field_validator("output_dir", "cache_dir", mode="after")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        """Expand `~` in path settings sourced from env or .env files."""
        return Path(value).expanduser()

    @property
    def assemblyai_configured(self) -> bool:
        """Whether ``ASSEMBLYAI_API_KEY`` is set in the environment.

        The AssemblyAI SDK reads the unprefixed env var on its own. Callers
        outside this module use this property for the budget gate's
        "is the key configured?" check so they never need to import ``os``.
        """
        return bool(os.getenv("ASSEMBLYAI_API_KEY"))

    def redacted_dump(self) -> dict[str, str]:
        """Return a dict of settings safe for logging and CLI output.

        Uses an explicit allowlist to ensure future API keys or secrets
        added to this model are never accidentally leaked.
        """
        allowlist = {
            "whisper_model_size",
            "whisper_device",
            "transcription_provider",
            "default_budget",
            "output_dir",
            "cache_dir",
            "cache_enabled",
            "keep_temp",
            "llm_model",
            "log_level",
        }
        return {k: str(v) for k, v in self.model_dump().items() if k in allowlist}


settings = TranscriberSettings()
