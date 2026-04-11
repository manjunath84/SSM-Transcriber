"""Transcriber CLI — entry point for all commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="transcriber",
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
        typer.Option("-f", "--format", help="Output format: txt | srt | md | json"),
    ] = "txt",
    quality: Annotated[
        str,
        typer.Option("-q", "--quality", help="Model quality: fast | balanced | best"),
    ] = "balanced",
    language: Annotated[
        str | None,
        typer.Option("-l", "--language", help="Language code, e.g. 'en'. Default: auto-detect"),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Skip cache and force re-transcription"),
    ] = False,
    budget: Annotated[
        str,
        typer.Option("--budget", help="Cost ceiling: free | low | best"),
    ] = "free",
    summarize: Annotated[
        bool,
        typer.Option("--summarize", help="Generate LLM summary after transcription"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("-y", "--yes", help="Skip cost confirmation prompts"),
    ] = False,
) -> None:
    """Transcribe audio or video from any supported source.

    Phase 0 stub — implementation lands in Phase 1. The command exits non-zero
    so shell scripts don't silently treat "not implemented" as success.
    """
    console.print("[yellow]Phase 1 not yet implemented.[/yellow]")
    console.print(f"  source    = {source}")
    console.print(f"  output    = {output or 'auto'}")
    console.print(f"  format    = {fmt}")
    console.print(f"  quality   = {quality}")
    console.print(f"  language  = {language or 'auto'}")
    console.print(f"  budget    = {budget}")
    console.print(f"  summarize = {summarize}")
    console.print(f"  cache     = {'disabled' if no_cache else 'enabled'}")
    console.print(f"  yes       = {yes}")
    raise typer.Exit(code=1)


# ── transcriber providers ─────────────────────────────────────────────────────

@app.command()
def providers() -> None:
    """List transcription providers registered via the provider registry.

    Phase 0 stub — the registry lands in Phase 5. Until then, only the
    built-in local provider is "available", and there is no registry to
    enumerate. This intentionally does NOT hardcode names or prices here
    to avoid teaching contributors to duplicate metadata outside the
    registry.
    """
    console.print(
        "[green]faster_whisper[/green]  local  $0.000/min  [dim](Phase 1)[/dim]\n"
        "[yellow]No provider registry yet — cloud providers land in Phase 5.[/yellow]"
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
    from transcriber.config import settings

    table = Table(title="Transcriber Settings", show_header=True, header_style="bold cyan")
    table.add_column("Setting", style="bold")
    table.add_column("Value")

    for key, value in settings.model_dump().items():
        table.add_row(f"TRANSCRIBER_{key.upper()}", str(value))

    console.print(table)


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
