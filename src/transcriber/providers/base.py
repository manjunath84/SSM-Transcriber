"""Transcription provider abstraction — Slice 1 has only AssemblyAI.

Phase 5 generalizes this with the provider registry, per-provider
cost-estimation hook, and ``--budget`` routing. For Slice 1, the
abstraction is intentionally thin: the contract this slice's CLI and
formatter consume, and that the AssemblyAI implementation honours.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


def _noop(_: str) -> None:
    """Default ``on_job_id`` callback when the caller doesn't care."""
    return None


@dataclass(frozen=True)
class Segment:
    """A single utterance / paragraph in the transcript timeline."""

    start_ms: int
    end_ms: int
    text: str
    speaker: str | None


@dataclass(frozen=True)
class TranscriptResult:
    """What the formatter consumes; what the provider returns."""

    text: str
    segments: list[Segment]
    language: str
    duration_seconds: float
    model: str
    job_id: str


class ProviderError(RuntimeError):
    """Provider-side failure (auth, retries exhausted, polling timeout, job
    error). CLI maps this to exit code 3."""


class TranscriptionProvider(ABC):
    """Contract every transcription provider implements."""

    @abstractmethod
    def transcribe(
        self,
        wav_path: Path,
        *,
        language: str | None,
        diarize: bool,
        speech_model: str,
        on_job_id: Callable[[str], None] = _noop,
    ) -> TranscriptResult:
        """Transcribe the WAV at ``wav_path`` and return the result.

        ``on_job_id`` fires once, immediately after the provider has a
        durable identifier for the job, so the CLI can surface it for
        recovery before the polling loop blocks.
        """
