"""Transciber CLI — entry point for all commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="transciber",
    help="Transcribe audio/video from local files, YouTube, or Google Drive.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


# ── transciber transcribe ────────────────────────────────────────────────────

@app.command()
def transcribe(
    source: Annotated[str, typer.Argument(help="File path, YouTube URL, or drive://FILE_ID")],
    output: Annotated[Path | None, typer.Option("-o", "--output", help="Output file path")] = None,
    format: Annotated[str, typer.Option("-f", "--format", help="Output format: txt | srt | md | json")] = "txt",
    quality: Annotated[str, typer.Option("-q", "--quality", help="Model quality: fast | balanced | best")] = "balanced",
    language: Annotated[str | None, typer.Option("-l", "--language", help="Language code, e.g. 'en'. Default: auto-detect")] = None,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache and force re-transcription")] = False,
    budget: Annotated[str, typer.Option("--budget", help="Cost ceiling: free | low | best")] = "free",
    summarize: Annotated[bool, typer.Option("--summarize", help="Generate LLM summary after transcription")] = False,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Skip cost confirmation prompts")] = False,
) -> None:
    """Transcribe audio or video from any supported source."""
    console.print("[yellow]Phase 1 not yet implemented.[/yellow]")
    console.print(f"  source   = {source}")
    console.print(f"  format   = {format}")
    console.print(f"  quality  = {quality}")
    console.print(f"  language = {language or 'auto'}")
    console.print(f"  budget   = {budget}")
    console.print(f"  cache    = {'disabled' if no_cache else 'enabled'}")
    raise typer.Exit(code=0)


# ── transciber providers ─────────────────────────────────────────────────────

@app.command()
def providers() -> None:
    """List available transcription providers and their status."""
    table = Table(title="Transcription Providers", show_header=True, header_style="bold cyan")
    table.add_column("Provider", style="bold")
    table.add_column("Type")
    table.add_column("Cost/min")
    table.add_column("Status")

    table.add_row("faster_whisper", "local", "$0.000", "[green]available (no key needed)[/green]")
    table.add_row("deepgram",       "cloud", "$0.006", "[yellow]Phase 5 — not yet implemented[/yellow]")
    table.add_row("assemblyai",     "cloud", "$0.009", "[yellow]Phase 5 — not yet implemented[/yellow]")
    table.add_row("openai_whisper", "cloud", "$0.020", "[yellow]Phase 5 — not yet implemented[/yellow]")

    console.print(table)


# ── transciber auth ──────────────────────────────────────────────────────────

@app.command()
def auth(
    service: Annotated[str, typer.Argument(help="Service to authenticate: google-drive")],
) -> None:
    """Authenticate with an external service (e.g. Google Drive OAuth)."""
    console.print(f"[yellow]Auth for '{service}' not yet implemented (Phase 4).[/yellow]")
    raise typer.Exit(code=0)


# ── transciber config ────────────────────────────────────────────────────────

@app.command()
def config() -> None:
    """Show current configuration (reads from .env and environment)."""
    console.print("[yellow]Config command not yet implemented (Phase 1).[/yellow]")
    console.print("Create a [bold].env[/bold] file from [bold].env.example[/bold] to configure.")
    raise typer.Exit(code=0)


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
