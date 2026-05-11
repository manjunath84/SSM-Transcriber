"""Title validation + filename-stem normalization.

Two helpers used by both the CLI (validating ``--title``) and the Drive
source layer (validating the filename auto-resolved from the public
download URL's ``Content-Disposition`` header). Lives in ``core/``
because both consumers need it; keeping it in ``cli`` would force a
``cli ↔ sources.google_drive`` circular import.

The split is intentional:

- ``validate_title`` returns the **display form** (whitespace stripped
  at the edges, internal whitespace preserved). Lands in YAML
  frontmatter as ``title:``.
- ``title_to_stem`` collapses internal whitespace runs to ``-`` for
  use in the output filename. Caller is responsible for validating
  first; this helper does no validation of its own.
"""

from __future__ import annotations

import re

_TITLE_FORBIDDEN_SUBSTRINGS = ("/", "\\", "\0", "..")


def validate_title(title: str) -> str:
    """Return the display form of a title (``--title`` or auto-resolved).

    Strips leading/trailing whitespace; preserves internal whitespace so
    the YAML ``title:`` field round-trips meaningful spacing. Raises
    ``ValueError`` with the documented "unsafe filename characters"
    message on path-traversal characters (``/``, ``\\``, NUL, ``..``),
    a leading dot (would create a hidden file), or any C0 control
    character or DEL — those would corrupt YAML frontmatter when written
    as a ``title:`` flow scalar.

    The ``..`` substring rejection is intentionally conservative
    (validation case 26a explicitly tests ``"ok..bad"`` as rejected,
    even though it isn't path traversal alone). Spec policy decision —
    don't relax without re-opening the spec.
    """
    stripped = title.strip()
    if not stripped:
        raise ValueError(
            f"--title contains unsafe filename characters: {title!r}"
        )
    if stripped.startswith("."):
        raise ValueError(
            f"--title contains unsafe filename characters: {title!r}"
        )
    for forbidden in _TITLE_FORBIDDEN_SUBSTRINGS:
        if forbidden in stripped:
            raise ValueError(
                f"--title contains unsafe filename characters: {title!r}"
            )
    # C0 control characters (0x00-0x1f) corrupt YAML flow scalars when
    # written as ``title: ...``: a literal newline splits the value
    # mid-scalar, a carriage return + line feed pair swaps in unicode
    # bidi marks. DEL (0x7f) is outside printable ASCII. NUL is already
    # caught above via _TITLE_FORBIDDEN_SUBSTRINGS, but listing the
    # complete C0 + DEL range here is the clean way to express the
    # invariant rather than relying on two overlapping checks.
    if any(ord(c) < 0x20 or ord(c) == 0x7f for c in stripped):
        raise ValueError(
            f"--title contains unsafe filename characters: {title!r}"
        )
    return stripped


def title_to_stem(title: str) -> str:
    """Collapse internal whitespace runs to ``-`` for a filename stem.

    Caller is responsible for validating the title with ``validate_title``
    first; this helper does no validation. Splitting the responsibilities
    keeps the YAML display form separate from the filename-friendly form.
    """
    return re.sub(r"\s+", "-", title)
