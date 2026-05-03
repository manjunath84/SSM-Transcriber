"""Audio extraction — source media → 16 kHz mono WAV in the workspace.

The canonical audio path runs against the *full* WAV (no VAD pre-strip);
that keeps sentence-level timestamps aligned with the original media. VAD
is a sidecar concern handled inside the transcription engine, not here
(see ``docs/PLAN.md`` §"VAD as a sidecar artifact").
"""

from __future__ import annotations

import logging
from pathlib import Path

import ffmpeg

from transcriber.core.workspace import RunWorkspace

logger = logging.getLogger(__name__)


class AudioExtractError(RuntimeError):
    """Raised when ffmpeg/ffprobe is missing or the source has no audio."""


def extract(source_path: Path, workspace: RunWorkspace) -> tuple[Path, float]:
    """Extract a 16 kHz mono PCM-s16le WAV into ``workspace``.

    Returns the WAV path and the source duration in seconds (from
    ``ffprobe``). The duration is the *raw* media duration, not the
    VAD-derived speech duration — that distinction matters for cost
    estimation, where the raw value is documented as an upper bound.
    """
    wav_path = workspace.path("audio.wav")
    duration = _probe_duration(source_path)

    try:
        (
            ffmpeg.input(str(source_path))
            .output(
                str(wav_path),
                ac=1,
                ar=16000,
                acodec="pcm_s16le",
                vn=None,
            )
            .overwrite_output()
            .run(quiet=True, capture_stdout=True, capture_stderr=True)
        )
    except FileNotFoundError as exc:
        raise AudioExtractError(
            "ffmpeg executable not found on PATH. Install ffmpeg "
            "(e.g. `brew install ffmpeg`) and retry."
        ) from exc
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise AudioExtractError(f"ffmpeg failed to extract audio: {stderr.strip()}") from exc

    logger.info("Extracted %.2fs of audio to %s", duration, wav_path)
    return wav_path, duration


def _probe_duration(source_path: Path) -> float:
    """Return the source duration in seconds via ``ffprobe``.

    Raises ``AudioExtractError`` on missing-binary or no-format-section
    cases so the CLI can map both to exit code 4 (local error).
    """
    try:
        meta = ffmpeg.probe(str(source_path))
    except FileNotFoundError as exc:
        raise AudioExtractError(
            "ffprobe executable not found on PATH. Install ffmpeg "
            "(e.g. `brew install ffmpeg`) and retry."
        ) from exc
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise AudioExtractError(f"ffprobe failed: {stderr.strip()}") from exc

    fmt = meta.get("format") or {}
    duration_str = fmt.get("duration")
    if duration_str is None:
        raise AudioExtractError(
            f"No duration in ffprobe output for {source_path}; "
            "the file may be corrupt or have no media streams."
        )
    return float(duration_str)
