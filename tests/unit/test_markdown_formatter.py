"""Tests for ``formatters/markdown.py``.

Covers cases 20-22 in validation.md: golden-file byte-for-byte equality,
``--no-speakers`` strips speaker prefixes, ``--no-timestamps`` strips
timestamp prefixes.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from transcriber.core.workspace import RunWorkspace
from transcriber.formatters.markdown import render
from transcriber.providers.base import Segment, TranscriptResult
from transcriber.sources.base import PreparedMedia

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "golden" / "sample.md"


@pytest.fixture
def workspace() -> Iterator[RunWorkspace]:
    with RunWorkspace() as ws:
        yield ws


def _media(workspace: RunWorkspace) -> PreparedMedia:
    return PreparedMedia(
        kind="local",
        original_uri="./interview.mp4",
        local_path=Path("/abs/path/interview.mp4"),
        title="interview",
        duration_seconds=None,
        workspace=workspace,
        extra={},
    )


def _result_diarized() -> TranscriptResult:
    return TranscriptResult(
        text="Hello. World.",
        segments=[
            Segment(start_ms=0, end_ms=14000, text="Hello.", speaker="A"),
            Segment(start_ms=14000, end_ms=28500, text="World.", speaker="B"),
        ],
        language="en",
        duration_seconds=28.5,
        model="universal-3-pro",
        job_id="job-abc",
    )


def test_render_golden_byte_for_byte(workspace: RunWorkspace) -> None:
    """Case 20: render against fixed input matches the committed golden file
    exactly. If this assertion ever needs updating, regenerate the golden
    file with the same fixed input — never edit it by hand to match a code
    change without auditing the diff."""
    media = _media(workspace)
    result = _result_diarized()
    output = render(result, media, created=date(2026, 5, 3))

    expected = GOLDEN_PATH.read_text(encoding="utf-8")
    assert output == expected


def test_render_no_speakers_strips_speaker_prefixes(workspace: RunWorkspace) -> None:
    """Case 21: include_speakers=False omits the **Speaker A:** prefix."""
    output = render(
        _result_diarized(),
        _media(workspace),
        include_speakers=False,
        created=date(2026, 5, 3),
    )
    assert "**Speaker A:**" not in output
    assert "**Speaker B:**" not in output
    # Timestamps are still on by default.
    assert "[00:00]" in output


def test_render_no_timestamps_strips_timestamp_prefixes(workspace: RunWorkspace) -> None:
    """Case 22: include_timestamps=False omits the [mm:ss] prefix."""
    output = render(
        _result_diarized(),
        _media(workspace),
        include_timestamps=False,
        created=date(2026, 5, 3),
    )
    assert "[00:00]" not in output
    assert "[00:14]" not in output
    # Speaker prefixes are still on by default.
    assert "**Speaker A:**" in output


def test_render_neither_speakers_nor_timestamps(workspace: RunWorkspace) -> None:
    """Both flags off → bare segment text in the body."""
    output = render(
        _result_diarized(),
        _media(workspace),
        include_speakers=False,
        include_timestamps=False,
        created=date(2026, 5, 3),
    )
    body = output.split("## Transcript\n", 1)[1]
    # Lines should be just the segment text.
    assert "Hello." in body
    assert "World." in body
    assert "[" not in body  # no timestamps
    assert "**" not in body  # no speaker bold
