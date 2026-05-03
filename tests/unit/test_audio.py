"""Tests for ``core/audio.py`` — ffmpeg/ffprobe wrapper and its guard rails.

These tests mock ``ffmpeg-python`` rather than calling the real binary,
so they run on systems without ffmpeg installed.
"""

from __future__ import annotations

from pathlib import Path

import ffmpeg
import pytest

from transcriber.core import audio
from transcriber.core.audio import AudioExtractError
from transcriber.core.workspace import RunWorkspace


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunWorkspace:
    """Use a deterministic tmp dir as the workspace root so we can assert
    on the produced WAV path without crossing into ``/tmp``."""
    monkeypatch.setattr("tempfile.mkdtemp", lambda prefix=None: str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    return RunWorkspace()


@pytest.fixture
def source(tmp_path: Path) -> Path:
    p = tmp_path / "input.mp4"
    p.write_bytes(b"fake-mp4-bytes")
    return p


def test_probe_zero_duration_raises(
    workspace: RunWorkspace, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero-duration must raise: otherwise estimate_assemblyai_cost(0) = $0,
    silently bypassing the soft cap and uploading anyway."""
    monkeypatch.setattr(ffmpeg, "probe", lambda _path: {"format": {"duration": "0.000000"}})

    with pytest.raises(AudioExtractError, match="zero/negative duration"):
        audio.extract(source, workspace)


def test_probe_negative_duration_raises(
    workspace: RunWorkspace, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence against malformed ffprobe output reporting negative duration."""
    monkeypatch.setattr(ffmpeg, "probe", lambda _path: {"format": {"duration": "-1.5"}})

    with pytest.raises(AudioExtractError, match="zero/negative duration"):
        audio.extract(source, workspace)


def test_probe_missing_duration_raises(
    workspace: RunWorkspace, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `format.duration` key (e.g. silent video container) raises clearly."""
    monkeypatch.setattr(ffmpeg, "probe", lambda _path: {"format": {}})

    with pytest.raises(AudioExtractError, match="No duration"):
        audio.extract(source, workspace)


def test_probe_binary_missing_raises(
    workspace: RunWorkspace, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ffprobe binary missing → exit 4 with a useful install hint."""

    def _raise(_path: str) -> object:
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(ffmpeg, "probe", _raise)

    with pytest.raises(AudioExtractError, match="ffprobe.*not found"):
        audio.extract(source, workspace)


def test_extract_zero_byte_wav_raises(
    workspace: RunWorkspace, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ffmpeg can succeed with a 0-byte WAV (e.g. video-only source). Reject
    so we don't ship an empty upload to AssemblyAI that would silently bill
    for zero-content audio."""
    monkeypatch.setattr(ffmpeg, "probe", lambda _path: {"format": {"duration": "12.5"}})

    class _FakeStream:
        def output(self, *_args: object, **_kwargs: object) -> _FakeStream:
            return self

        def overwrite_output(self) -> _FakeStream:
            return self

        def run(self, **_kwargs: object) -> tuple[bytes, bytes]:
            # Touch the WAV path to "exist" but stay 0 bytes.
            wav = workspace.path("audio.wav")
            wav.write_bytes(b"")
            return b"", b""

    monkeypatch.setattr(ffmpeg, "input", lambda _path: _FakeStream())

    with pytest.raises(AudioExtractError, match="empty WAV"):
        audio.extract(source, workspace)
