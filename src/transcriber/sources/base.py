"""Source contract — every input source returns the same shape.

Per F2 in ``docs/PLAN.md``, ``PreparedMedia`` is the contract that Phase 1
(local), Phase 2 (YouTube), and Phase 4 (Google Drive) all return so the
pipeline downstream is source-agnostic.

Slice 2 extended F2 additively: ``local_path`` is now ``Path | None`` and a
new ``remote_url: str | None`` field lands. Validation: exactly one of the
two must be set. ``LocalSource`` keeps populating ``local_path`` and leaves
``remote_url`` ``None``; ``DriveSource`` does the opposite. The provider
branches once on ``media.remote_url`` — if set, AssemblyAI fetches the URL
itself (``audio_url`` ingestion, no upload); else the existing upload flow
runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from transcriber.core.workspace import RunWorkspace


SourceKind = Literal["local", "youtube", "google_drive"]


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
