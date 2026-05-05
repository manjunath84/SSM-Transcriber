"""Local-file source — wraps a path on disk into ``PreparedMedia``."""

from __future__ import annotations

from pathlib import Path

from transcriber.core.workspace import RunWorkspace
from transcriber.sources.base import PreparedMedia, SourceInputError


class LocalSource:
    """Resolve a local-file path into a ``PreparedMedia``.

    No copying or workspace writes happen here. The user's file stays where
    it is; the resolved absolute path is what later stages read from.
    Validation surfaces missing or non-file paths as exceptions the CLI
    can map to its exit-code policy.
    """

    @staticmethod
    def prepare(
        uri: str, workspace: RunWorkspace, *, title: str | None = None
    ) -> PreparedMedia:
        """Validate the path and wrap it in ``PreparedMedia``.

        ``duration_seconds`` is left ``None``; ``audio.extract`` is the
        single place that calls ``ffprobe`` to populate it, so we do not
        probe twice.

        ``title`` overrides the filename-stem default when set (the CLI
        passes the validated ``--title`` here). Otherwise the title is
        derived from the local file's stem.

        Raises ``FileNotFoundError`` if the path doesn't exist (CLI exit 4)
        or ``SourceInputError`` if the path is not a regular file
        (CLI exit 2). The latter is a ``ValueError`` subclass, so any
        existing ``except ValueError`` will continue to catch it.
        """
        path = Path(uri).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")
        if not path.is_file():
            raise SourceInputError(f"Source is not a file: {path}")

        resolved = path.resolve()
        return PreparedMedia(
            kind="local",
            original_uri=uri,
            local_path=resolved,
            title=title if title is not None else resolved.stem,
            duration_seconds=None,
            workspace=workspace,
            extra={},
        )
