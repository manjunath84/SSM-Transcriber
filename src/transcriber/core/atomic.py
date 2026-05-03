"""Atomic output writes and collision resolution.

Per F5 in ``docs/PLAN.md``, output files are written via a temp file in
the destination directory, then ``os.replace``-d into place. The temp
file lives next to the destination — not in ``RunWorkspace`` — so the
rename never crosses filesystems (e.g. ``/tmp`` vs the user's home),
which would fail with ``EXDEV`` on Linux.
"""

from __future__ import annotations

import os
from pathlib import Path


def write_text_atomic(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically.

    Steps: ensure parent dir exists; write to a sibling ``.tmp`` file;
    ``os.replace`` into the final path. On any failure, the partial
    ``.tmp`` is removed and any pre-existing file at ``path`` is left
    intact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding=encoding)
        os.replace(tmp, path)
    except BaseException:
        # ``BaseException`` so KeyboardInterrupt also triggers cleanup.
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def resolve_collision(path: Path) -> Path:
    """Return ``path`` if free, else the next available ``stem-N.suffix``.

    Suffix increment policy from the spec: re-runs accumulate as ``-2``,
    ``-3``, etc. so the previous transcript is never overwritten.
    """
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    n = 2
    while True:
        candidate = parent / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1
