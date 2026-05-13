"""Tests for the frozen dataclasses in ``providers/base.py``.

The ``__post_init__`` validators are defence-in-depth: the provider
already protects most invalid inputs at the HTTP boundary, but a buggy
vendor response or a future provider implementation could still construct
a degenerate ``Segment`` or ``TranscriptResult``. Catching that at
construction time gives us a clear ``ValueError`` instead of a confusing
downstream rendering failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transcriber.errors import TranscriberError
from transcriber.providers.base import Segment, TranscriptResult
from transcriber.sources.base import PreparedMedia, SourceInputError


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
            provider="assemblyai",
            model="universal-3-pro",
            job_id="x",
        )


def test_transcript_result_carries_provider_for_youtube_captions() -> None:
    """Phase 2 Slice 1: TranscriptResult.provider is required; model and
    job_id are Optional[str] because the YouTube captions path has no
    ASR model (auto-captions don't expose the underlying engine) and no
    remote job ID (the transcript is fetched directly, no provider job
    is created)."""
    result = TranscriptResult(
        text="hello world",
        segments=[],
        language="en",
        duration_seconds=1.5,
        provider="youtube-captions",
        model=None,
        job_id=None,
    )
    assert result.provider == "youtube-captions"
    assert result.model is None
    assert result.job_id is None


def test_transcript_result_assemblyai_shape_still_works() -> None:
    """Regression: AssemblyAI's TranscriptResult (provider+model+job_id
    all strings) keeps validating identically. This guards against the
    Optional migration accidentally relaxing the AssemblyAI side too."""
    result = TranscriptResult(
        text="x",
        segments=[],
        language="en",
        duration_seconds=1.0,
        provider="assemblyai",
        model="universal-3-pro",
        job_id="abc123",
    )
    assert result.provider == "assemblyai"
    assert result.model == "universal-3-pro"
    assert result.job_id == "abc123"


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


# ---------------------------------------------------------------------------
# PreparedMedia (sources/base.py) — F2 contract Slice 2 extension.
# Validation: exactly one of local_path / remote_url must be set.
# ---------------------------------------------------------------------------


def _media_kwargs(**overrides: object) -> dict[str, object]:
    """Build PreparedMedia kwargs with safe defaults; tests override fields."""
    from transcriber.core.workspace import RunWorkspace

    base: dict[str, object] = {
        "kind": "google_drive",
        "original_uri": "drive://X",
        "local_path": None,
        "remote_url": "https://drive.usercontent.google.com/download?id=X&export=download&confirm=t",
        "title": None,
        "duration_seconds": None,
        "workspace": RunWorkspace(),
        "extra": {},
    }
    base.update(overrides)
    return base


def test_prepared_media_rejects_both_local_path_and_remote_url(
    tmp_path: Path,
) -> None:
    """Setting both fields violates the XOR invariant — a single transcribe
    call would have two answers to "where does the audio come from?"."""
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"")
    with pytest.raises(ValueError, match="exactly one of local_path"):
        PreparedMedia(**_media_kwargs(kind="local", local_path=wav))  # type: ignore[arg-type]


def test_prepared_media_rejects_neither_local_path_nor_remote_url() -> None:
    """Neither field set → no audio source at all → invariant violation."""
    with pytest.raises(ValueError, match="exactly one of local_path"):
        PreparedMedia(**_media_kwargs(remote_url=None))  # type: ignore[arg-type]


def test_prepared_media_accepts_local_path_only(tmp_path: Path) -> None:
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"")
    media = PreparedMedia(**_media_kwargs(kind="local", local_path=wav, remote_url=None))  # type: ignore[arg-type]
    assert media.local_path == wav
    assert media.remote_url is None


def test_prepared_media_accepts_remote_url_only() -> None:
    media = PreparedMedia(**_media_kwargs())  # type: ignore[arg-type]
    assert media.local_path is None
    assert media.remote_url == "https://drive.usercontent.google.com/download?id=X&export=download&confirm=t"


def test_source_input_error_is_value_error_subclass() -> None:
    """Existing ``except ValueError`` callers must keep catching
    SourceInputError. The CLI uses the subtype to distinguish user
    input from PreparedMedia invariant violations (review I7)."""
    assert issubclass(SourceInputError, ValueError)


# ---------------------------------------------------------------------------
# PreparedTranscript (sources/base.py) — F2 contract Phase 2 Slice 1 extension.
# Sibling dataclass to PreparedMedia for sources that produce a finished
# TranscriptResult without going through a provider (YouTube captions).
# ---------------------------------------------------------------------------


def test_prepared_transcript_carries_finished_transcript() -> None:
    """The captions path emits a PreparedTranscript with a
    TranscriptResult already in hand; no provider, no audio."""
    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.base import PreparedTranscript

    workspace = RunWorkspace()
    result = TranscriptResult(
        text="hi",
        segments=[],
        language="en",
        duration_seconds=1.0,
        provider="youtube-captions",
        model=None,
        job_id=None,
    )
    pt = PreparedTranscript(
        kind="youtube_captions",
        original_uri="https://youtu.be/abc",
        transcript=result,
        title="Test Title",
        workspace=workspace,
        extra={"video_id": "abc", "caption_type": "manual"},
    )
    assert pt.kind == "youtube_captions"
    assert pt.original_uri == "https://youtu.be/abc"
    assert pt.transcript is result
    assert pt.title == "Test Title"
    assert pt.extra["caption_type"] == "manual"


def test_prepared_source_protocol_structural_conformance() -> None:
    """Both PreparedMedia and PreparedTranscript expose the five shared
    attributes the PreparedSource Protocol declares. ``hasattr`` rather
    than ``isinstance(x, PreparedSource)`` because the Protocol's primary
    purpose is static mypy typing, not runtime dispatch (we'd need
    ``@runtime_checkable`` for isinstance, and gain nothing from it)."""
    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.base import PreparedTranscript

    workspace = RunWorkspace()
    media = PreparedMedia(**_media_kwargs())  # type: ignore[arg-type]
    transcript_obj = PreparedTranscript(
        kind="youtube_captions",
        original_uri="https://youtu.be/abc",
        transcript=TranscriptResult(
            text="",
            segments=[],
            language="en",
            duration_seconds=0.0,
            provider="youtube-captions",
            model=None,
            job_id=None,
        ),
        title=None,
        workspace=workspace,
        extra={},
    )
    for obj in (media, transcript_obj):
        for attr in ("kind", "original_uri", "title", "workspace", "extra"):
            assert hasattr(obj, attr), f"{type(obj).__name__} missing {attr!r}"
