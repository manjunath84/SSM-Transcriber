"""SSM-Transcriber CLI — entry point for all commands.

Slice 1 wires the ``transcribe`` command end-to-end for the local-file →
AssemblyAI → markdown path. Other source resolvers (YouTube, Drive),
local providers (faster-whisper), and other formatters (txt / srt /
json) land in their own phases.
"""

from __future__ import annotations

from datetime import date
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
from transcriber.sources.local import LocalSource

app = typer.Typer(
    name="ssm-transcriber",
    help="Transcribe audio/video from local files, YouTube, or Google Drive.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


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
        str,
        typer.Option("--budget", help="Cost ceiling: free | low | best"),
    ] = "free",
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
            # Resolve source (local only in Slice 1).
            try:
                media = LocalSource.prepare(source, workspace)
            except FileNotFoundError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=4) from exc
            except ValueError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=2) from exc

            # Extract audio + duration via ffprobe.
            try:
                wav_path, duration_seconds = extract_audio(media.local_path, workspace)
            except AudioExtractError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=4) from exc

            # Two-gate spend check.
            cost_usd = estimate_assemblyai_cost(duration_seconds)
            try:
                proceed = budget_check(
                    provider_name="AssemblyAI",
                    budget=budget,
                    key_configured=settings.assemblyai_configured,
                    cost_usd=cost_usd,
                    yes=yes,
                    prompt=lambda msg: Confirm.ask(msg, default=False, console=console),
                    notify=lambda msg: console.print(msg),
                )
            except BudgetError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=2) from exc
            if not proceed:
                console.print("[yellow]Cancelled by user; no charge incurred.[/yellow]")
                raise typer.Exit(code=0)

            # Provider call.
            provider = AssemblyAIProvider(max_wait_seconds=max_wait * 60)
            try:
                result = provider.transcribe(
                    wav_path,
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
                stem = media.local_path.stem
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
    raise typer.Exit(code=1)


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
