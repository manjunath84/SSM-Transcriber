"""Source contract — every input source returns the same shape.

Per F2 in ``docs/PLAN.md``, the source layer produces an artifact the
pipeline downstream consumes uniformly. F2 has been extended additively
twice:

- Slice 2 (Drive): ``PreparedMedia.local_path`` became ``Path | None``
  and a new ``remote_url: str | None`` field landed for URL-passthrough
  sources. ``LocalSource`` sets ``local_path``; ``DriveSource`` sets
  ``remote_url``; provider branches once.
- Phase 2 Slice 1 (YouTube captions): a sibling ``PreparedTranscript``
  dataclass joined ``PreparedMedia``. Captions sources produce a
  finished ``TranscriptResult`` without going through a provider —
  modelling that as a third mode on ``PreparedMedia`` would make the
  "media" name dishonest. A ``PreparedSource`` Protocol captures the
  five shared metadata fields both dataclasses expose; the CLI
  branches on ``isinstance(prepared, PreparedTranscript)`` before
  invoking the budget router.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from transcriber.core.workspace import RunWorkspace
    from transcriber.providers.base import TranscriptResult


SourceKind = Literal["local", "youtube", "youtube_captions", "google_drive"]


class SourceInputError(ValueError):
    """User-input error from a source layer.

    Distinguishes user-actionable failures (malformed URI, missing file,
    file path is a directory) from ``PreparedMedia`` invariant violations
    (producer bug — both fields set or neither). The CLI catches this
    specifically and maps to exit 2 ("user input error"); a plain
    ``ValueError`` from ``PreparedMedia.__post_init__`` is left to bubble
    with a traceback so a misbehaving Source implementation surfaces
    loudly during development rather than as an opaque "exit 2" with the
    invariant message shown to end users.

    Subclassing ``ValueError`` keeps backward compatibility with any
    existing ``pytest.raises(ValueError, match=...)`` tests.
    """


class PreparedSource(Protocol):
    """Shared shape of everything a source's ``prepare()`` may return.

    ``PreparedMedia`` and ``PreparedTranscript`` both conform structurally;
    no explicit inheritance is needed because Python's ``Protocol`` checks
    attribute shape, not nominal type. The formatter and CLI accept
    ``PreparedSource`` so they can render either flavour uniformly,
    while the provider abstraction stays typed on the concrete
    ``PreparedMedia`` — mypy enforces that the captions path never
    reaches a provider call.
    """

    kind: SourceKind
    original_uri: str
    title: str | None
    workspace: RunWorkspace
    extra: dict[str, str]


@dataclass(frozen=True)
class PreparedMedia:
    """Everything downstream stages need to transcribe a piece of media.

    The ``workspace`` field owns cleanup — the caller that created the
    ``PreparedMedia`` owns the ``RunWorkspace`` and is responsible for
    cleanup on both success and failure (see F5 in ``docs/PLAN.md``).

    ``local_path`` and ``remote_url`` are mutually exclusive: exactly one
    must be set. ``LocalSource`` sets ``local_path``; ``DriveSource`` sets
    ``remote_url``.
    """

    kind: SourceKind
    original_uri: str
    local_path: Path | None
    title: str | None
    duration_seconds: float | None
    workspace: RunWorkspace
    extra: dict[str, str]
    remote_url: str | None = None

    def __post_init__(self) -> None:
        has_local = self.local_path is not None
        has_remote = self.remote_url is not None
        if has_local == has_remote:
            raise ValueError(
                "PreparedMedia requires exactly one of local_path or "
                "remote_url to be set; got "
                f"local_path={self.local_path!r}, remote_url={self.remote_url!r}"
            )


@dataclass(frozen=True)
class PreparedTranscript:
    """A finished transcript produced by a source without provider involvement.

    Used by sources where the transcription work happens at fetch time —
    Phase 2 Slice 1's ``YouTubeSource`` is the first instance, returning
    a ``TranscriptResult`` built from YouTube's existing caption track.
    The pipeline branches on ``isinstance(prepared, PreparedTranscript)``
    and hands ``transcript`` straight to the formatter; provider and
    budget gate are skipped entirely.

    Source-specific metadata (caption type, video ID, etc.) lives in
    ``extra`` so this dataclass stays source-agnostic — a future
    ``OtterSource`` or ``NotebookLMImportSource`` reuses the same shape
    without dishonest fields.
    """

    kind: SourceKind
    original_uri: str
    transcript: TranscriptResult
    title: str | None
    workspace: RunWorkspace
    extra: dict[str, str]
