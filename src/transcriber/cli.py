"""SSM-Transcriber CLI — entry point for all commands.

Slice 1 wires the ``transcribe`` command end-to-end for the local-file →
AssemblyAI → markdown path. Other source resolvers (YouTube, Drive),
local providers (faster-whisper), and other formatters (txt / srt /
json) land in their own phases.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from transcriber.config import settings
from transcriber.core import atomic
from transcriber.core.audio import AudioExtractError, extract as extract_audio
from transcriber.core.budget import (
    BudgetError,
    check as budget_check,
    estimate_assemblyai_cost,
)
from transcriber.core.workspace import RunWorkspace
from transcriber.formatters import markdown as md_formatter
from transcriber.providers.assemblyai import AssemblyAIProvider
from transcriber.providers.base import ProviderError
from transcriber.sources import resolve_source
from transcriber.sources.base import SourceInputError


class Budget(StrEnum):
    """Budget tier for ``--budget``. Typer rejects values outside this set
    at parse time, so a typo like ``--budget paind`` fails before any
    paid call can be authorised. ``StrEnum`` (Python 3.11+) gives every
    member ``str`` semantics, so comparisons and ``budget.value`` work
    identically to a plain ``str + Enum`` pair."""

    free = "free"
    low = "low"
    best = "best"

# Library code uses ``logger.info`` / ``logger.warning`` everywhere (job IDs,
# retry attempts, polling status, RunWorkspace cleanup failures). Without
# ``basicConfig`` those records go nowhere by default — wire it once at the
# CLI entry point so library logs reach stderr.
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

app = typer.Typer(
    name="ssm-transcriber",
    help="Transcribe audio/video from local files, YouTube, or Google Drive.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _confirm_or_decline(msg: str) -> bool:
    """Wrap ``Confirm.ask`` so closed stdin (Ctrl-D, piped input ended) is
    treated as a "no" instead of crashing with an uncaught ``EOFError``."""
    try:
        return Confirm.ask(msg, default=False, console=console)
    except EOFError:
        return False


# ── --title sanitization (Slice 2) ───────────────────────────────────────────
#
# atomic.write_text_atomic creates parent directories on demand. An
# unsanitized --title "../foo" would let a user (or a misuse) write outside
# settings.output_dir. _validate_title rejects path-traversal characters at
# the CLI boundary so the source layer / formatter never see an unsafe value.
#
# The helpers are split:
#   _validate_title -> the display form (whitespace stripped at the edges,
#                      internal whitespace preserved). This lands in YAML
#                      frontmatter as ``title:``.
#   _title_to_stem  -> collapses internal whitespace to ``-`` for use in the
#                      output filename. Caller is responsible for validating
#                      first; this helper does no validation of its own.

_TITLE_FORBIDDEN_SUBSTRINGS = ("/", "\\", "\0", "..")


def _validate_title(title: str) -> str:
    """Return the display form of a user-provided ``--title`` value.

    Strips leading/trailing whitespace; preserves internal whitespace so
    the YAML ``title:`` field round-trips what the user typed. Raises
    ``ValueError`` with the documented "unsafe filename characters"
    message on path-traversal characters (``/``, ``\\``, NUL, ``..``)
    or a leading dot (would create a hidden file).
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
    return stripped


def _title_to_stem(title: str) -> str:
    """Collapse internal whitespace runs to ``-`` for a filename stem.

    Caller is responsible for validating the title with ``_validate_title``
    first; this helper does no validation. Splitting the responsibilities
    keeps the YAML display form separate from the filename-friendly form.
    """
    return re.sub(r"\s+", "-", title)


# ── transcriber transcribe ────────────────────────────────────────────────────

@app.command()
def transcribe(
    source: Annotated[
        str,
        typer.Argument(help="File path, YouTube URL, or drive://FILE_ID"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Output file path"),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("-f", "--format", help="Output format (Slice 1: md only)"),
    ] = "md",
    language: Annotated[
        str | None,
        typer.Option("-l", "--language", help="Language code, e.g. 'en'. Default: auto-detect"),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option(
            "--title",
            help="Frontmatter + filename stem (Drive sources). Defaults to file ID.",
        ),
    ] = None,
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help="AssemblyAI speech model: universal-3-pro (default) | universal-2",
        ),
    ] = "universal-3-pro",
    no_speakers: Annotated[
        bool,
        typer.Option("--no-speakers", help="Disable speaker diarization (default: on)"),
    ] = False,
    no_timestamps: Annotated[
        bool,
        typer.Option("--no-timestamps", help="Strip mm:ss timestamp prefixes (default: on)"),
    ] = False,
    budget: Annotated[
        Budget,
        typer.Option("--budget", help="Cost ceiling: free | low | best"),
    ] = Budget.free,
    max_wait: Annotated[
        int,
        typer.Option("--max-wait", help="Polling cap in minutes (default: 30)"),
    ] = 30,
    keep_temp: Annotated[
        bool,
        typer.Option("--keep-temp", help="Preserve workspace temp dir for debugging"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("-y", "--yes", help="Skip cost confirmation prompts"),
    ] = False,
) -> None:
    """Transcribe audio or video from any supported source."""
    if fmt != "md":
        console.print(f"[red]error:[/red] only --format md is supported in Slice 1 (got '{fmt}').")
        raise typer.Exit(code=2)

    keep = keep_temp or settings.keep_temp
    try:
        with RunWorkspace(keep=keep) as workspace:
            # Resolve the source. Dispatcher reject-not-swallows unknown
            # :// URIs (exit 2) so the user gets a clear "URI scheme not
            # supported" rather than a misleading "file not found" from
            # LocalSource fallthrough.
            try:
                source_cls = resolve_source(source)
            except SourceInputError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=2) from exc

            # Validate --title up-front so source.prepare() gets a clean
            # string. Validation rejects path-traversal characters before
            # the source layer or atomic.write_text_atomic ever sees them.
            display_title: str | None
            if title is not None:
                try:
                    display_title = _validate_title(title)
                except ValueError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=2) from exc
            else:
                display_title = None

            # Prepare the source with the validated title. Each source
            # decides how to use it: LocalSource overrides the filename-
            # stem default; DriveSource stores it for the formatter.
            #
            # Catch SourceInputError specifically (NOT bare ValueError):
            # PreparedMedia.__post_init__ raises plain ValueError for
            # invariant violations (producer bug — both fields set, or
            # neither). Letting that bubble with a traceback surfaces the
            # bug to the developer rather than showing the dataclass
            # invariant message to the end user as exit 2 (review I7).
            try:
                media = source_cls.prepare(source, workspace, title=display_title)
            except FileNotFoundError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=4) from exc
            except SourceInputError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=2) from exc

            # Branch: Drive passthrough skips ffmpeg + per-call cost
            # estimate; local upload runs both.
            if media.remote_url is not None:
                # Drive variant: Gate 1 + Gate 2 still fire via the
                # standard budget_check; the cost-estimate notify is
                # overridden via cost_summary because we have no local
                # duration to estimate against. Soft-cap silenced too.
                try:
                    proceed = budget_check(
                        provider_name="AssemblyAI",
                        budget=budget.value,
                        key_configured=settings.assemblyai_configured,
                        cost_usd=0.0,  # unused when cost_summary is set
                        yes=yes,
                        prompt=_confirm_or_decline,
                        notify=lambda msg: console.print(msg),
                        cost_summary=(
                            "Provider: AssemblyAI · URL passthrough — "
                            "AssemblyAI bills per-minute against the public "
                            "URL; exact cost in the AssemblyAI dashboard "
                            "after the run."
                        ),
                    )
                except BudgetError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=2) from exc
                if not proceed:
                    console.print(
                        "[yellow]Cancelled by user; no charge incurred.[/yellow]"
                    )
                    raise typer.Exit(code=0)
            else:
                # Local path: existing extract + budget flow.
                if media.local_path is None:
                    # Defence-in-depth: PreparedMedia.__post_init__ guarantees
                    # exactly-one-of (local_path, remote_url) is set; reaching
                    # this branch means a Source produced an inconsistent shape.
                    raise RuntimeError(
                        "PreparedMedia invariant violated: "
                        "local source has no local_path."
                    )

                try:
                    wav_path, duration_seconds = extract_audio(
                        media.local_path, workspace
                    )
                except AudioExtractError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=4) from exc

                # C1 fix: thread the canonical 16 kHz mono WAV back into
                # ``media`` so the provider uploads the extracted audio,
                # NOT the original .mp4 / .m4a / etc. Without this swap the
                # AssemblyAI upload path silently regresses Slice 1's
                # "extract → normalised WAV → upload" contract: the provider
                # would receive ``media.local_path`` (= original source) and
                # upload it. AssemblyAI accepts any audio container, so the
                # regression is invisible at runtime past mocks but degrades
                # transcription quality on any local source whose container
                # isn't already AssemblyAI's preferred shape.
                media = dataclasses.replace(media, local_path=wav_path)

                cost_usd = estimate_assemblyai_cost(duration_seconds)
                try:
                    proceed = budget_check(
                        provider_name="AssemblyAI",
                        budget=budget.value,
                        key_configured=settings.assemblyai_configured,
                        cost_usd=cost_usd,
                        yes=yes,
                        prompt=_confirm_or_decline,
                        notify=lambda msg: console.print(msg),
                    )
                except BudgetError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=2) from exc
                if not proceed:
                    console.print(
                        "[yellow]Cancelled by user; no charge incurred.[/yellow]"
                    )
                    raise typer.Exit(code=0)

            # Provider call.
            provider = AssemblyAIProvider(max_wait_seconds=max_wait * 60)
            try:
                result = provider.transcribe(
                    media,
                    language=language,
                    diarize=not no_speakers,
                    speech_model=model,
                    on_job_id=lambda job_id: console.print(
                        f"[cyan]AssemblyAI job ID:[/cyan] {job_id}"
                    ),
                )
            except ProviderError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=3) from exc

            # Render markdown.
            content = md_formatter.render(
                result,
                media,
                include_speakers=not no_speakers,
                include_timestamps=not no_timestamps,
            )

            # Resolve output path with collision-suffix policy.
            if output is None:
                if display_title is not None:
                    # Whitespace in --title becomes - in the filename;
                    # YAML title preserves the original.
                    stem = _title_to_stem(display_title)
                elif media.local_path is not None:
                    stem = media.local_path.stem
                else:
                    # Drive source, no --title: fall back to the file ID.
                    # extra['drive_file_id'] is set by DriveSource.prepare;
                    # missing key is a producer-side bug, not user input.
                    # Let KeyError bubble with traceback rather than
                    # silently writing 'untitled-DATE.md' (review I5).
                    stem = media.extra["drive_file_id"]
                date_str = date.today().isoformat()
                output = settings.output_dir / f"{stem}-{date_str}.md"
            output = atomic.resolve_collision(output)

            try:
                atomic.write_text_atomic(output, content)
            except OSError as exc:
                console.print(f"[red]error:[/red] failed to write output: {exc}")
                raise typer.Exit(code=4) from exc

            console.print(f"[green]✓[/green] Saved to: {output}")
    except KeyboardInterrupt:
        # Standard SIGINT exit code; workspace cleanup runs via __exit__.
        console.print("[yellow]Interrupted.[/yellow]")
        raise typer.Exit(code=130) from None


# ── transcriber providers ─────────────────────────────────────────────────────

@app.command()
def providers() -> None:
    """List transcription providers registered via the provider registry.

    Phase 0/Slice 1 stub — the registry lands in Phase 5. Until then,
    AssemblyAI is hardcoded into the transcribe command.
    """
    console.print(
        "[green]assemblyai[/green]  cloud  $0.009/min  "
        "[dim](Slice 1; via --budget low|best)[/dim]\n"
        "[yellow]No provider registry yet — Phase 5 generalizes this.[/yellow]"
    )


# ── transcriber auth ──────────────────────────────────────────────────────────

@app.command()
def auth(
    service: Annotated[str, typer.Argument(help="Service to authenticate: google-drive")],
) -> None:
    """Authenticate with an external service (e.g. Google Drive OAuth)."""
    console.print(f"[yellow]Auth for '{service}' not yet implemented (Phase 4).[/yellow]")
    # Exit 2 = config / usage error per validation.md exit-code matrix
    # ({0,2,3,4}). Originally 1 (outside the documented matrix).
    raise typer.Exit(code=2)


# ── transcriber config ────────────────────────────────────────────────────────

@app.command()
def config() -> None:
    """Show current configuration (reads from .env and TRANSCRIBER_* env vars)."""
    table = Table(title="Transcriber Settings", show_header=True, header_style="bold cyan")
    table.add_column("Setting", style="bold")
    table.add_column("Value")

    for key, value in settings.redacted_dump().items():
        table.add_row(f"TRANSCRIBER_{key.upper()}", str(value))

    console.print(table)


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
