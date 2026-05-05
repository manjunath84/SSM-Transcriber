"""Google Drive source — URL passthrough only (Slice 2).

This module accepts five URL forms documented in
``specs/2026-05-04-drive-source-passthrough/requirements.md`` §"Reference
calls (verbatim)" and returns a ``PreparedMedia`` whose ``remote_url`` is
the canonical Drive download URL AssemblyAI fetches directly. **No OAuth,
no local download, no upload.**

OAuth + private-file support is a deferred Slice 3; see ``docs/PLAN.md``
§"Phase 4 — Drive Source".
"""

from __future__ import annotations

import re

from transcriber.core.workspace import RunWorkspace
from transcriber.sources.base import PreparedMedia, SourceInputError

# Drive file IDs are URL-safe base64 — alnum, dash, underscore. The minimum
# length isn't documented but the shortest IDs we see in practice are 25+
# characters; we don't enforce a minimum to stay forward-compatible.
# Use ``fullmatch`` (not ``match`` + ``$``) — without re.MULTILINE the ``$``
# anchor would also match before a trailing ``\n``, letting ``"abc\n"``
# validate as a clean file ID. ``fullmatch`` requires the entire candidate
# string to match, no newline edge case.
_FILE_ID_RE = re.compile(r"[A-Za-z0-9_-]+")

# `/file/d/<ID>/...` — extract the ID segment regardless of trailing path.
_FILE_D_RE = re.compile(r"/file/d/([A-Za-z0-9_-]+)(?:/|$)")

# `?id=<ID>` or `&id=<ID>` — extract the ID query parameter value.
_ID_QUERY_RE = re.compile(r"[?&]id=([A-Za-z0-9_-]+)")


def _extract_file_id(uri: str) -> str:
    """Extract the Drive file ID from any of the five accepted URL forms.

    Raises ``SourceInputError`` (subclass of ``ValueError`` for back-compat
    with existing ``pytest.raises(ValueError, ...)`` tests) if the URI
    doesn't match any form or yields an empty / invalid file ID. Failure
    mode is loud-and-correct: a user who pastes a Drive folder URL or a
    malformed link gets a clear error rather than a silent fallthrough to
    AssemblyAI returning a 4xx.
    """
    if uri.startswith("drive://"):
        candidate = uri[len("drive://"):]
        if candidate and _FILE_ID_RE.fullmatch(candidate):
            return candidate
        raise SourceInputError(
            f"could not extract a Drive file ID from {uri!r}: "
            "drive:// URIs must contain a non-empty alphanumeric ID."
        )

    if uri.startswith(("https://drive.google.com/", "http://drive.google.com/")):
        if match := _FILE_D_RE.search(uri):
            return match.group(1)
        if match := _ID_QUERY_RE.search(uri):
            return match.group(1)
        raise SourceInputError(
            f"could not extract a Drive file ID from {uri!r}: "
            "Drive URL must include /file/d/<ID> or ?id=<ID>."
        )

    raise SourceInputError(
        f"could not extract a Drive file ID from {uri!r}: "
        "expected drive://FILE_ID or https://drive.google.com/..."
    )


class DriveSource:
    """Wrap a Drive URL into ``PreparedMedia`` for URL-passthrough mode.

    Defence-in-depth: ``prepare`` validates the URL itself even though
    ``resolve_source`` already rejects non-Drive ``://`` URIs at dispatch.
    Tests call ``DriveSource.prepare`` directly without the dispatcher,
    and a future programmatic caller may also bypass dispatch. Same
    boundary pattern as ``providers/assemblyai.py`` re-checking the API
    key after the budget gate.
    """

    @staticmethod
    def prepare(
        uri: str, workspace: RunWorkspace, *, title: str | None = None
    ) -> PreparedMedia:
        file_id = _extract_file_id(uri)
        remote_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        return PreparedMedia(
            kind="google_drive",
            original_uri=f"drive://{file_id}",
            local_path=None,
            remote_url=remote_url,
            title=title,
            duration_seconds=None,
            workspace=workspace,
            extra={"drive_file_id": file_id},
        )
