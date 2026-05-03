"""Tests for the frozen dataclasses in ``providers/base.py``.

The ``__post_init__`` validators are defence-in-depth: the provider
already protects most invalid inputs at the HTTP boundary, but a buggy
vendor response or a future provider implementation could still construct
a degenerate ``Segment`` or ``TranscriptResult``. Catching that at
construction time gives us a clear ``ValueError`` instead of a confusing
downstream rendering failure.
"""

from __future__ import annotations

import pytest

from transcriber.errors import TranscriberError
from transcriber.providers.base import Segment, TranscriptResult


def test_segment_rejects_negative_start() -> None:
    with pytest.raises(ValueError, match="start_ms must be >= 0"):
        Segment(start_ms=-1, end_ms=100, text="x", speaker=None)


def test_segment_rejects_end_before_start() -> None:
    with pytest.raises(ValueError, match="must be >= start_ms"):
        Segment(start_ms=100, end_ms=50, text="x", speaker=None)


def test_segment_accepts_zero_duration_segment() -> None:
    """A segment with start == end is degenerate but representable (e.g. a
    silent placeholder); it's not an error class. The downstream renderer
    can choose to skip or display it."""
    seg = Segment(start_ms=0, end_ms=0, text="", speaker=None)
    assert seg.start_ms == 0


def test_transcript_result_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="duration_seconds must be >= 0"):
        TranscriptResult(
            text="",
            segments=[],
            language="auto",
            duration_seconds=-1.0,
            model="universal-3-pro",
            job_id="x",
        )


def test_provider_errors_inherit_from_transcriber_error() -> None:
    """A future caller wanting to handle "any transcriber-domain failure"
    uniformly (logging, metrics) can catch ``TranscriberError`` once
    instead of listing all subclasses."""
    from transcriber.core.audio import AudioExtractError
    from transcriber.core.budget import BudgetError
    from transcriber.providers.base import ProviderError

    assert issubclass(BudgetError, TranscriberError)
    assert issubclass(ProviderError, TranscriberError)
    assert issubclass(AudioExtractError, TranscriberError)
