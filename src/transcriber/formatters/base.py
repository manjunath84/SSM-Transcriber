"""Formatter protocol — Slice 1 has only Markdown.

Phase 3 adds the txt / srt / json formatters and a ``get_formatter(name)``
factory; for Slice 1, the Protocol exists so the CLI can type its
formatter parameter without importing the markdown module directly.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from transcriber.providers.base import TranscriptResult
from transcriber.sources.base import PreparedMedia


class Formatter(Protocol):
    """Renders a ``TranscriptResult`` + ``PreparedMedia`` into a string."""

    def render(
        self,
        result: TranscriptResult,
        media: PreparedMedia,
        *,
        include_speakers: bool = True,
        include_timestamps: bool = True,
        created: date | None = None,
    ) -> str: ...
