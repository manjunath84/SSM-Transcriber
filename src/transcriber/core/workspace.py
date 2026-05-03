"""Per-run temp directory with deterministic cleanup.

Per F5 in ``docs/PLAN.md``: every CLI invocation creates exactly one
``RunWorkspace``. Sources and the audio extractor write under
``workspace.path("…")``; nobody else calls ``tempfile.mkdtemp``. Cleanup
runs in ``__exit__`` so a Ctrl-C (SIGINT) propagating out of the ``with``
block still removes the temp dir, unless ``keep`` is set for debugging.

Atomic *output* writes (``.tmp`` + ``os.replace`` in the destination
directory, not the workspace) are a separate concern handled by the
caller — see F5 for the rationale on cross-device renames.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from types import TracebackType

logger = logging.getLogger(__name__)


class RunWorkspace:
    """Context manager owning one temp directory for the lifetime of a run."""

    root: Path

    def __init__(self, *, keep: bool = False, prefix: str = "transcriber-") -> None:
        self._keep = keep
        self._prefix = prefix
        # ``mkdtemp`` is called eagerly so callers can read ``self.root`` even
        # without entering the context manager (useful in tests).
        self.root = Path(tempfile.mkdtemp(prefix=self._prefix))

    def path(self, name: str) -> Path:
        """Return a path under ``root`` for a workspace-internal artifact."""
        return self.root / name

    def __enter__(self) -> RunWorkspace:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._keep:
            logger.info("RunWorkspace preserved at %s (keep_temp=True)", self.root)
            return
        # Best-effort cleanup, but log every failure so a permission error or
        # held file handle is visible rather than silently leaking the temp
        # directory across runs. ``onexc`` is the 3.12+ replacement for the
        # deprecated ``onerror`` callback.
        shutil.rmtree(self.root, onexc=self._log_cleanup_failure)

    def _log_cleanup_failure(
        self,
        _func: object,
        path: str,
        exc_info: BaseException,
    ) -> None:
        logger.warning(
            "RunWorkspace cleanup failed for %s: %s. The workspace temp "
            "directory may persist on disk and require manual removal.",
            path,
            exc_info,
        )
