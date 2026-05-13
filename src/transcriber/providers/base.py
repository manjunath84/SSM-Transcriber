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
from typing import TYPE_CHECKING

from transcriber.errors import TranscriberError

if TYPE_CHECKING:
    # Type-only import to break the cycle:
    #   providers.base ← sources.base ← sources.__init__ ← sources.youtube ← providers.base
    # YouTubeSource added this loop in Phase 2 Slice 1; resolving via
    # TYPE_CHECKING keeps the abstract base typed without runtime import.
    from transcriber.sources.base import PreparedMedia


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

    def __post_init__(self) -> None:
        if self.start_ms < 0:
            raise ValueError(f"Segment.start_ms must be >= 0, got {self.start_ms}")
        if self.end_ms < self.start_ms:
            raise ValueError(
                f"Segment.end_ms ({self.end_ms}) must be >= start_ms ({self.start_ms})"
            )


@dataclass(frozen=True)
class TranscriptResult:
    """What the formatter consumes; what the provider returns.

    Phase 2 Slice 1 generalized this to support non-AssemblyAI sources:
    ``provider`` is the canonical identifier for who produced the
    transcript (``"assemblyai"``, ``"youtube-captions"``, ...). ``model``
    and ``job_id`` are ``str | None`` because the captions path has no
    ASR model identifier and no remote job to reference.
    """

    text: str
    segments: list[Segment]
    language: str
    duration_seconds: float
    provider: str
    model: str | None
    job_id: str | None

    def __post_init__(self) -> None:
        if self.duration_seconds < 0:
            raise ValueError(
                "TranscriptResult.duration_seconds must be >= 0, "
                f"got {self.duration_seconds}"
            )


class ProviderError(TranscriberError):
    """Provider-side failure (auth, retries exhausted, polling timeout, job
    error). CLI maps this to exit code 3."""


class TranscriptionProvider(ABC):
    """Contract every transcription provider implements."""

    @abstractmethod
    def transcribe(
        self,
        media: PreparedMedia,
        *,
        language: str | None,
        diarize: bool,
        speech_model: str,
        on_job_id: Callable[[str], None] = _noop,
    ) -> TranscriptResult:
        """Transcribe ``media`` and return the result.

        If ``media.remote_url`` is set, the implementation should pass
        that URL to the provider's URL-ingestion endpoint (no upload).
        Otherwise it uploads ``media.local_path`` and transcribes that.

        ``on_job_id`` fires once, immediately after the provider has a
        durable identifier for the job, so the CLI can surface it for
        recovery before the polling loop blocks.
        """
