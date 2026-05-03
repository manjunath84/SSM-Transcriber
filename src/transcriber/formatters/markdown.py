"""Markdown formatter — produces the ``.md`` artifact users save.

Output shape is the user-visible contract specified in
``specs/2026-05-02-assemblyai-mvp-slice-1/requirements.md`` §"Output
frontmatter contract": general-purpose YAML frontmatter (Obsidian /
NotebookLM / paste-into-AI friendly) plus a body with optional
``[mm:ss]`` timestamps and ``**Speaker A:**`` prefixes.
"""

from __future__ import annotations

from datetime import date

from transcriber.providers.base import TranscriptResult
from transcriber.sources.base import PreparedMedia

# YAML scalars whose bare form would be parsed as a non-string by most YAML
# loaders. Quoting these keeps the field a string round-trip.
_YAML_RESERVED_WORDS = frozenset(
    {"null", "true", "false", "yes", "no", "on", "off", "~"}
)


def render(
    result: TranscriptResult,
    media: PreparedMedia,
    *,
    include_speakers: bool = True,
    include_timestamps: bool = True,
    created: date | None = None,
) -> str:
    """Render the transcript as markdown with a YAML frontmatter block.

    ``created`` is injectable so golden tests are deterministic; production
    callers leave it ``None`` and the formatter uses today's date.
    """
    if created is None:
        created = date.today()

    diarized_speakers: set[str] = {s.speaker for s in result.segments if s.speaker}
    speakers_count = len(diarized_speakers) if diarized_speakers else None
    title = media.title or media.local_path.stem

    frontmatter = _frontmatter(
        title=title,
        media=media,
        result=result,
        diarized=bool(diarized_speakers),
        speakers_count=speakers_count,
        created=created,
    )
    body = _body(
        title=title,
        media=media,
        result=result,
        include_speakers=include_speakers,
        include_timestamps=include_timestamps,
        diarized_speakers=diarized_speakers,
    )
    return frontmatter + "\n" + body


def _frontmatter(
    *,
    title: str,
    media: PreparedMedia,
    result: TranscriptResult,
    diarized: bool,
    speakers_count: int | None,
    created: date,
) -> str:
    """Render the YAML frontmatter block, in stable field order."""
    speakers_value = "null" if speakers_count is None else str(speakers_count)
    fields: list[tuple[str, str]] = [
        ("title", _yaml_string(title)),
        ("source_uri", _yaml_string(_source_uri(media))),
        ("source_kind", _yaml_string(media.kind)),
        ("duration_seconds", f"{result.duration_seconds:.1f}"),
        ("language", _yaml_string(result.language)),
        ("provider", _yaml_string("assemblyai")),
        ("model", _yaml_string(result.model)),
        ("diarized", "true" if diarized else "false"),
        ("speakers", speakers_value),
        ("assemblyai_job_id", _yaml_string(result.job_id)),
        ("created", _yaml_string(created.isoformat())),
    ]
    lines = ["---"] + [f"{k}: {v}" for k, v in fields] + ["---", ""]
    return "\n".join(lines)


def _body(
    *,
    title: str,
    media: PreparedMedia,
    result: TranscriptResult,
    include_speakers: bool,
    include_timestamps: bool,
    diarized_speakers: set[str],
) -> str:
    """Render the H1, summary blockquote, and transcript section."""
    minutes = result.duration_seconds / 60.0
    diar_note = (
        f" · diarized ({len(diarized_speakers)} speakers)"
        if diarized_speakers
        else ""
    )
    summary = (
        f"> Transcribed from `{media.original_uri}` · {minutes:.1f} min · "
        f"{result.language} · assemblyai/{result.model}{diar_note}."
    )

    lines: list[str] = [f"# {title}", "", summary, "", "## Transcript", ""]

    for seg in result.segments:
        prefix_parts: list[str] = []
        if include_timestamps:
            prefix_parts.append(_format_timestamp(seg.start_ms))
        if include_speakers and seg.speaker:
            prefix_parts.append(f"**Speaker {seg.speaker}:**")
        prefix = " ".join(prefix_parts)
        line = f"{prefix} {seg.text}".strip() if prefix else seg.text
        lines.append(line)
        lines.append("")

    # Trim trailing blank lines, then enforce a single terminal newline.
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def _source_uri(media: PreparedMedia) -> str:
    """Return the canonical ``source_uri`` for the frontmatter field."""
    if media.kind == "local":
        return media.local_path.as_uri()
    return media.original_uri


def _format_timestamp(ms: int) -> str:
    """Format a timestamp as ``[mm:ss]`` (mm rolls over past 60 — fine for
    the MVP; an hh:mm:ss variant lands when transcripts >1h are common)."""
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"[{minutes:02d}:{seconds:02d}]"


def _yaml_string(value: str) -> str:
    """Render a string as bare YAML when safe, double-quoted otherwise.

    Plain (unquoted) scalars look cleanest but YAML 1.2 has several
    contexts that change the parse mid-string. Quoting matters for:

    - empty strings, leading/trailing whitespace
    - YAML reserved words (``null``, ``true``, etc.)
    - ISO dates (``YYYY-MM-DD`` would be parsed as a date object)
    - strings starting with reserved indicators (``- ? @ % & * ! | > ' " [ ] { } # ,``)
    - embedded ``": "`` (colon+space) — the mapping-value separator,
      which would split the scalar and corrupt the parse
    - embedded ``" #"`` (space+hash) — starts a comment in plain context,
      truncating the value at the hash
    - trailing ``":"`` — looks like an empty mapping value

    Filename-derived titles like ``Lecture: Intro`` and ``foo # bar`` hit
    the latter two; the body of the function below is the only thing
    standing between user filenames and broken-but-silent frontmatter.
    """
    if not value:
        return '""'
    if value != value.strip():
        return _double_quote(value)
    if value.lower() in _YAML_RESERVED_WORDS:
        return _double_quote(value)
    if _looks_like_iso_date(value):
        return _double_quote(value)
    if value[0] in "-?@`%&*!|>'\"[]{}#," or value.startswith(": "):
        return _double_quote(value)
    if ": " in value or " #" in value:
        return _double_quote(value)
    if value.endswith(":"):
        return _double_quote(value)
    return value


def _double_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _looks_like_iso_date(value: str) -> bool:
    """Match ``YYYY-MM-DD`` exactly (the shape YAML loaders treat as a date)."""
    return (
        len(value) == 10
        and value[4] == "-"
        and value[7] == "-"
        and value[:4].isdigit()
        and value[5:7].isdigit()
        and value[8:10].isdigit()
    )
