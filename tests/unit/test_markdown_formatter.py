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


@pytest.mark.parametrize(
    "title",
    [
        "Lecture: Intro",  # embedded `: ` would split the YAML mapping
        "foo # bar",  # ` #` starts a comment in plain scalar context
        "trailing-colon:",  # trailing `:` looks like an empty mapping value
        "ends with #",  # ends with hash
    ],
)
def test_yaml_frontmatter_quotes_unsafe_titles(
    workspace: RunWorkspace, title: str
) -> None:
    """Filename-derived titles can contain ``:``, ``#`` etc. Unquoted, the
    YAML parser silently truncates or splits them. The formatter must
    double-quote any title with these embedded indicators so the produced
    frontmatter is valid YAML round-trip — Obsidian / NotebookLM / paste-
    into-AI all break on broken frontmatter.
    """
    media = PreparedMedia(
        kind="local",
        original_uri=f"./{title}.mp4",
        local_path=Path(f"/abs/{title}.mp4"),
        title=title,
        duration_seconds=10.0,
        workspace=workspace,
        extra={},
    )
    result = TranscriptResult(
        text="hi",
        segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
        language="en",
        duration_seconds=10.0,
        model="universal-3-pro",
        job_id="j",
    )

    output = render(result, media, created=date(2026, 5, 3))

    # The title line must be the literal double-quoted form; this is the
    # round-trip-safe way to express any of the unsafe scalars above.
    expected_line = f'title: "{title}"'
    assert expected_line in output, f"expected {expected_line!r} in:\n{output}"


# ---------------------------------------------------------------------------
# Slice 2: Drive-shaped PreparedMedia (local_path=None, remote_url set).
# ---------------------------------------------------------------------------


def _drive_media(workspace: RunWorkspace, *, title: str | None) -> PreparedMedia:
    return PreparedMedia(
        kind="google_drive",
        original_uri="drive://1Zdp9aYV",
        local_path=None,
        remote_url="https://drive.usercontent.google.com/download?id=1Zdp9aYV&export=download&confirm=t",
        title=title,
        duration_seconds=None,
        workspace=workspace,
        extra={"drive_file_id": "1Zdp9aYV"},
    )


def test_render_drive_media_uses_drive_source_uri(workspace: RunWorkspace) -> None:
    """Case 27: Drive-shaped media renders source_uri as drive://FILE_ID
    (NOT file:///), source_kind google_drive, and uses the title."""
    media = _drive_media(workspace, title="Session 17")
    output = render(_result_diarized(), media, created=date(2026, 5, 3))

    assert "source_uri: drive://1Zdp9aYV" in output
    assert "source_kind: google_drive" in output
    assert "title: Session 17" in output
    # No file:// URL should appear anywhere in the output.
    assert "file://" not in output


def test_render_drive_media_falls_back_to_file_id_when_no_title(
    workspace: RunWorkspace,
) -> None:
    """No --title on a Drive source → render() falls back to extra['drive_file_id'].
    Per review I4: that lookup uses [] not .get(default), so a producer-side
    bug (Source returning kind='google_drive' without populating extra) raises
    KeyError loudly instead of silently producing 'untitled'."""
    media = _drive_media(workspace, title=None)
    output = render(_result_diarized(), media, created=date(2026, 5, 3))

    assert "title: 1Zdp9aYV" in output
    assert "# 1Zdp9aYV" in output


def test_render_drive_media_missing_file_id_raises_loud(
    workspace: RunWorkspace,
) -> None:
    """Review I4 invariant: if a producer (e.g., a future Drive variant)
    constructs PreparedMedia(kind='google_drive') without populating
    extra['drive_file_id'], the formatter must fail loud — not silently
    write 'untitled-DATE.md'."""
    media = PreparedMedia(
        kind="google_drive",
        original_uri="drive://X",
        local_path=None,
        remote_url="https://drive.usercontent.google.com/download?id=X&export=download&confirm=t",
        title=None,
        duration_seconds=None,
        workspace=workspace,
        extra={},  # missing drive_file_id — producer bug
    )
    with pytest.raises(KeyError, match="drive_file_id"):
        render(_result_diarized(), media, created=date(2026, 5, 3))


def test_source_uri_raises_for_local_kind_with_none_local_path(
    workspace: RunWorkspace,
) -> None:
    """Review I6 invariant: PreparedMedia(kind='local', local_path=None) is
    impossible per __post_init__, but if a buggy Source ever constructed it,
    the formatter must raise — not silently return original_uri (which is
    raw user input, not a file:// URI)."""
    from transcriber.formatters.markdown import _source_uri

    # Bypass __post_init__ via dataclasses.replace on a valid instance —
    # this is the only way to reach the unreachable state for testing.
    valid = PreparedMedia(
        kind="local",
        original_uri="./video.mp4",
        local_path=Path("/abs/path/video.mp4"),
        title=None,
        duration_seconds=None,
        workspace=workspace,
        extra={},
    )
    # Build an invariant-violating instance by going around __post_init__:
    # use object.__setattr__ on the frozen dataclass to simulate a bug.
    object.__setattr__(valid, "local_path", None)
    with pytest.raises(ValueError, match="source-implementation bug"):
        _source_uri(valid)
