"""Source contract — every input source returns the same shape.

Per F2 in ``docs/PLAN.md``, ``PreparedMedia`` is the contract that Phase 1
(local), Phase 2 (YouTube), Phase 4 (Google Drive) all return so the
pipeline downstream is source-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from transcriber.core.workspace import RunWorkspace


SourceKind = Literal["local", "youtube", "google_drive"]


@dataclass(frozen=True)
class PreparedMedia:
    """Everything downstream stages need to transcribe a piece of media.

    The ``workspace`` field owns cleanup — the caller that created the
    ``PreparedMedia`` owns the ``RunWorkspace`` and is responsible for
    cleanup on both success and failure (see F5 in ``docs/PLAN.md``).
    """

    kind: SourceKind
    original_uri: str
    local_path: Path
    title: str | None
    duration_seconds: float | None
    workspace: RunWorkspace
    extra: dict[str, str]
