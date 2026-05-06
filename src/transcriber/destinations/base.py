"""OutputDestination Protocol — the upload interface for all destinations.

Java analogue: a single-method interface. Any class with an ``upload``
method of the right signature satisfies it without explicit inheritance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from transcriber.errors import TranscriberError


class DestinationError(TranscriberError):
    """Upload failed or destination misconfigured. CLI maps this to exit 2."""


class OutputDestination(Protocol):
    def upload(self, path: Path, filename: str) -> str:
        """Upload *path* to the destination. Returns a URL or location string."""
        ...
