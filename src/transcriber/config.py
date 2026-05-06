"""Transcriber configuration — pydantic-settings singleton.

All internal settings are prefixed ``TRANSCRIBER_``. Third-party API keys
(``ASSEMBLYAI_API_KEY``, ``DEEPGRAM_API_KEY``, ``OPENAI_API_KEY``, etc.) are
unprefixed by convention and read via ``os.getenv`` from the process
environment. ``pydantic-settings`` only loads ``.env`` values for declared
model fields (i.e. the ``TRANSCRIBER_*`` ones), so we eagerly call
``load_dotenv`` at module import to push every ``.env`` entry — including
unprefixed vendor keys — into ``os.environ`` before the singleton is built.
The ``assemblyai_configured`` boundary helper at the bottom of this module
plus ``providers/assemblyai.py:_api_headers`` are the only two sites that
read the AssemblyAI key from the environment; the rest of the codebase
routes through the property to honour the "never read os.environ directly"
rule from CLAUDE.md.

Slice 1 grew this beyond the Phase-0 stub: ``keep_temp``,
``assemblyai_configured``, and ``redacted_dump`` all live here now. Phase
5 will extend it again with the provider registry's per-provider key
boundaries (Deepgram, OpenAI Whisper, Hugging Face).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load `.env` into `os.environ` for unprefixed vendor keys (ASSEMBLYAI_API_KEY,
# etc.). `pydantic-settings` reads `.env` for declared TRANSCRIBER_* fields
# only, so this is the boundary where vendor keys actually become visible to
# `os.getenv`. `override=False` means real env vars win over the file.
#
# ``find_dotenv(usecwd=True)`` walks up from the *invocation cwd* rather
# than from this source file. Matters for two reasons: (1) when the
# package is installed (e.g. via `pip install`) the source lives in
# site-packages and the default file-relative search would silently miss
# the user's project `.env`; (2) test isolation — a test that ``chdir``s
# into a tmp dir before reloading this module needs the tmp dir's `.env`
# found, not whichever `.env` happens to sit next to the source tree.
load_dotenv(find_dotenv(usecwd=True), override=False)


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

    # ── Google Drive (upload destination) ────────────────────────────────────
    drive_output_folder_id: str | None = None

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    @field_validator("output_dir", "cache_dir", mode="after")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        """Expand `~` in path settings sourced from env or .env files."""
        return Path(value).expanduser()

    @property
    def assemblyai_configured(self) -> bool:
        """Whether ``ASSEMBLYAI_API_KEY`` is set (and non-blank) in the environment.

        ``providers/assemblyai.py:_api_headers`` is the only other site that
        reads this env var (at the HTTP boundary). Callers everywhere else
        route through this property so the rest of the codebase honours the
        "never read os.environ directly" rule from CLAUDE.md.

        Stripping whitespace before the truthiness check matters: a key like
        ``"   "`` would otherwise pass Gate 1, then fail with HTTP 401 only
        after the user has waited for ffmpeg extraction and confirmed cost.
        """
        return bool((os.getenv("ASSEMBLYAI_API_KEY") or "").strip())

    @property
    def google_oauth_configured(self) -> bool:
        """Whether GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET are set.

        Per CLAUDE.md conventions, OAuth credentials are third-party keys
        so they are read unprefixed from os.environ rather than via
        pydantic-settings' TRANSCRIBER_ prefix.
        """
        return (
            bool((os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip())
            and bool((os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip())
        )

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
            "drive_output_folder_id",
            "log_level",
        }
        return {k: str(v) for k, v in self.model_dump().items() if k in allowlist}


settings = TranscriberSettings()
