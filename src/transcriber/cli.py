"""SSM-Transcriber CLI — entry point for all commands.

Slice 1 wires the ``transcribe`` command end-to-end for the local-file →
AssemblyAI → markdown path. Other source resolvers (YouTube, Drive),
local providers (faster-whisper), and other formatters (txt / srt /
json) land in their own phases.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import requests
import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from youtube_transcript_api import YouTubeTranscriptApiException

from transcriber.config import settings
from transcriber.core import atomic
from transcriber.core.audio import AudioExtractError, extract as extract_audio
from transcriber.core.auth import AuthError, authenticate_drive, load_drive_credentials
from transcriber.core.budget import (
    BudgetError,
    check as budget_check,
    estimate_assemblyai_cost,
)
from transcriber.core.title import title_to_stem, validate_title
from transcriber.core.workspace import RunWorkspace
from transcriber.destinations.base import DestinationError
from transcriber.destinations.drive import DriveDestination
from transcriber.formatters import markdown as md_formatter
from transcriber.providers.assemblyai import AssemblyAIProvider
from transcriber.providers.base import ProviderError
from transcriber.sources import resolve_source
from transcriber.sources.base import PreparedTranscript, SourceInputError


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
logger = logging.getLogger(__name__)

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


def _no_captions_message(source_uri: str) -> str:
    """Build the documented no-captions error pointing at issue #21
    + offering a copy-paste yt-dlp workaround using Phase 1's free
    local path. Spec validation #53/#54."""
    return (
        f"Video has no usable captions:\n"
        f"  {source_uri}\n\n"
        f"Either the creator disabled captions or no auto-generated "
        f"track is available. Audio-download fallback (yt-dlp + local "
        f"ASR) is planned for Phase 2 Slice 2 — tracked at:\n"
        f"  https://github.com/manjunath84/SSM-Transcriber/issues/21\n\n"
        f"Workaround today (uses Phase 1 local ASR, $0):\n\n"
        f"  uv run yt-dlp -x --audio-format wav -o /tmp/audio.wav '{source_uri}'\n"
        f"  uv run ssm-transcriber transcribe /tmp/audio.wav"
    )


def _youtube_transcript_api_version() -> str:
    """Return the installed ``youtube-transcript-api`` version for use
    in user-facing error messages. Best-effort: returns ``"unknown"`` if
    metadata isn't available (e.g., editable install without dist info)."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("youtube-transcript-api")
    except PackageNotFoundError:
        return "unknown"


def _handle_youtube_exception(exc: Exception, source_uri: str) -> int:
    """Map a youtube-transcript-api exception to (exit_code) and print
    the documented user-facing message. Returns the exit code so the
    caller can ``raise typer.Exit(code=...)`` cleanly.

    Exit-code matrix (spec error matrix §Q5d):
    - 2: TranscriptsDisabled, NoTranscriptFound, VideoUnavailable,
         VideoUnplayable, InvalidVideoId, AgeRestricted,
         PoTokenRequired (user-facing "your URL / your video / your
         auth" problems that retrying won't help)
    - 3: IpBlocked, RequestBlocked, YouTubeRequestFailed,
         YouTubeDataUnparsable, FailedToCreateConsentCookie, cookie
         errors, generic catch-all (system / network / library
         conditions that aren't the user's URL)
    """
    from youtube_transcript_api import (
        AgeRestricted,
        CookieError,
        FailedToCreateConsentCookie,
        InvalidVideoId,
        NoTranscriptFound,
        PoTokenRequired,
        RequestBlocked,
        TranscriptsDisabled,
        VideoUnavailable,
        VideoUnplayable,
        YouTubeRequestFailed,
    )

    if isinstance(exc, (TranscriptsDisabled, NoTranscriptFound)):
        console.print(f"[red]error:[/red] {_no_captions_message(source_uri)}")
        return 2
    if isinstance(exc, PoTokenRequired):
        # PR-#31 silent-failure-hunter finding: previously routed to the
        # generic catch-all and told the user the library may need an
        # update — wrong diagnosis. The user needs cookies / PO-token,
        # which Slice 2's yt-dlp fallback can supply once it ships.
        console.print(
            f"[red]error:[/red] Video requires a PO-token / cookie-based "
            f"authentication that youtube-transcript-api can't provide:\n"
            f"  {source_uri}\n\n"
            f"Slice 2's yt-dlp fallback (issue #21) is the planned path "
            f"for videos that need browser-cookie auth."
        )
        return 2
    if isinstance(exc, AgeRestricted):
        console.print(
            f"[red]error:[/red] Video is age-restricted and requires "
            f"authentication that youtube-transcript-api doesn't support:\n"
            f"  {source_uri}\n\n"
            f"Slice 2's yt-dlp fallback can be configured with browser "
            f"cookies for age-restricted videos (--cookies-from-browser) "
            f"once that ships (issue #21)."
        )
        return 2
    if isinstance(exc, VideoUnavailable):
        console.print(
            f"[red]error:[/red] Video unavailable (gone, private, or "
            f"never existed):\n  {source_uri}"
        )
        return 2
    if isinstance(exc, VideoUnplayable):
        reason = getattr(exc, "reason", "no further detail")
        console.print(
            f"[red]error:[/red] Video unplayable: {reason}\n  {source_uri}"
        )
        return 2
    if isinstance(exc, InvalidVideoId):
        console.print(
            f"[red]error:[/red] YouTube rejected the video ID:\n  {source_uri}"
        )
        return 2
    if isinstance(exc, RequestBlocked):
        # IpBlocked is a subclass of RequestBlocked; this branch catches
        # both. Library version is named so the user can decide whether
        # to upgrade vs wait the rate-limit out.
        console.print(
            "[red]error:[/red] YouTube blocked the request from this IP. "
            "Try again later, or run from a different network. "
            f"(youtube-transcript-api {_youtube_transcript_api_version()})"
        )
        return 3
    if isinstance(exc, CookieError):
        # CookieError and its subclasses only fire when cookies are
        # passed to YouTubeTranscriptApi(...) — Slice 1 doesn't, but
        # this defensive arm future-proofs Slice 2's cookie path.
        console.print(
            f"[red]error:[/red] Cookie configuration error: {exc}\n"
            f"This is only reachable when --cookies-from-browser or an "
            f"explicit cookie file is provided; Slice 1 doesn't pass "
            f"either."
        )
        return 3
    # Diagnostic-neutral catch-all for the remaining
    # CouldNotRetrieveTranscript subclasses (YouTubeRequestFailed,
    # YouTubeDataUnparsable, FailedToCreateConsentCookie,
    # NotTranslatable, TranslationLanguageNotAvailable) — these are a
    # mix of transient network conditions, YouTube-side response shape
    # changes, and consent-flow issues. We don't try to disambiguate
    # them user-facing.
    if isinstance(exc, (YouTubeRequestFailed, FailedToCreateConsentCookie)):
        kind = "transient YouTube response" if isinstance(
            exc, YouTubeRequestFailed
        ) else "consent flow"
        console.print(
            f"[red]error:[/red] {kind} error from youtube-transcript-api "
            f"{_youtube_transcript_api_version()}: {exc}\n"
            f"Retrying after a few minutes often resolves these. If it "
            f"persists, check for a library update or open an issue."
        )
        return 3
    console.print(
        f"[red]error:[/red] Unexpected error from youtube-transcript-api "
        f"{_youtube_transcript_api_version()}: {type(exc).__name__}: {exc}\n"
        f"Rerun with TRANSCRIBER_LOG_LEVEL=DEBUG for more detail, or "
        f"open an issue if this persists."
    )
    return 3


# ── --title sanitization (Slice 2) ───────────────────────────────────────────
#
# atomic.write_text_atomic creates parent directories on demand. An
# unsanitized --title "../foo" would let a user (or a misuse) write outside
# settings.output_dir. validate_title rejects path-traversal characters at
# the CLI boundary so the source layer / formatter never see an unsafe value.
# See ``transcriber.core.title`` for the shared validate_title +
# title_to_stem helpers (also used by the Drive source layer to validate
# auto-resolved filenames from the public download URL's
# Content-Disposition header).


def _resolve_drive_folder(cli_folder: str | None) -> str:
    """Return the Drive folder ID from CLI flag or config. Exits 2 if neither set."""
    raw = cli_folder or settings.drive_output_folder_id
    folder = raw.strip() if raw else None
    if not folder:
        console.print(
            "[red]error:[/red] No Drive folder configured.\n"
            "Pass --drive-folder FOLDER_ID  or  set TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID in .env"
        )
        raise typer.Exit(code=2)
    return folder


# ── transcriber upload ────────────────────────────────────────────────────────

@app.command()
def upload(
    file: Annotated[Path, typer.Argument(help="Transcript file to upload to Google Drive")],
    drive_folder: Annotated[
        str | None,
        typer.Option(
            "--drive-folder",
            help="Drive folder ID (overrides TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID)",
        ),
    ] = None,
) -> None:
    """Upload an existing transcript file to Google Drive."""
    if not file.is_file():
        console.print(f"[red]error:[/red] File not found: {file}")
        raise typer.Exit(code=4)

    folder_id = _resolve_drive_folder(drive_folder)

    # AuthError (config: re-run auth google-drive) is exit 2; DestinationError
    # (network/API failure with file still on disk, retry possible) is exit 4.
    # Different exit codes let scripts distinguish "fix config" from "retry".
    try:
        dest = DriveDestination(folder_id=folder_id)
        url = dest.upload(file, file.name)
    except AuthError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    except DestinationError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=4) from exc

    console.print(f"Uploaded → {url}")


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
    upload_to_drive: Annotated[
        bool,
        typer.Option("--upload-to-drive", help="Upload the transcript to Google Drive after transcription"),  # noqa: E501
    ] = False,
    drive_folder: Annotated[
        str | None,
        typer.Option("--drive-folder", help="Drive folder ID (overrides TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID)"),  # noqa: E501
    ] = None,
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
                    display_title = validate_title(title)
                except ValueError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=2) from exc
            else:
                display_title = None

            # Fail fast: validate Drive folder and credentials before doing any
            # transcription work. Both checks run before audio extraction or any
            # paid API call so the user doesn't pay AssemblyAI only to discover
            # a Drive misconfiguration afterward.
            upload_folder_id: str | None = None
            if upload_to_drive:
                upload_folder_id = _resolve_drive_folder(drive_folder)
                try:
                    load_drive_credentials()
                except AuthError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=2) from exc

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
            except YouTubeTranscriptApiException as exc:
                # YouTube captions: library exception → spec-mapped exit
                # code + user-facing message. Catches the broad library
                # base so any new ``CouldNotRetrieveTranscript`` subclass
                # AND cookie-related exceptions (Slice 2 cookie-path
                # future-proofing) route through _handle_youtube_exception.
                code = _handle_youtube_exception(exc, source)
                raise typer.Exit(code=code) from exc
            except requests.RequestException as exc:
                # Network-layer exhaustion after tenacity retries on the
                # captions fetch. Catches the broad RequestException so
                # ChunkedEncodingError, TooManyRedirects, etc. are not
                # rethrown as raw tracebacks. CLI exit 3.
                console.print(
                    f"[red]error:[/red] Network error fetching captions: {exc}"
                )
                raise typer.Exit(code=3) from exc

            # Captions branch: PreparedTranscript carries a finished
            # TranscriptResult — skip the budget gate and provider
            # entirely (validation #50; the captions path is $0 by
            # construction). Falls through to the shared render + write
            # + optional upload block at the bottom of this function so
            # --upload-to-drive is honored for captions sources too
            # (Codex PR #31 review finding).
            if isinstance(media, PreparedTranscript):
                if language is not None:
                    logger.info(
                        "captions source: --language ignored, returned track is %s",
                        media.transcript.language,
                    )
                result = media.transcript
            else:
                # PreparedMedia path — budget gate + provider call.
                # Drive passthrough skips ffmpeg + per-call cost estimate;
                # local upload runs both.
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
                    # AssemblyAI upload path silently breaks Slice 1's
                    # "extract → normalised WAV → upload" contract: the provider
                    # would receive ``media.local_path`` (= original source) and
                    # upload it. The follow-up advisor pass caught a second
                    # concrete cost: ``media.local_path.stem`` in the output-
                    # filename derivation would land on ``audio`` (the workspace
                    # WAV's stem) instead of the source's stem. AssemblyAI
                    # accepts most audio containers, so quality differences
                    # between original and canonical WAV depend on AssemblyAI's
                    # internal pipeline and aren't directly verifiable from this
                    # PR — the contract violation and filename regression are.
                    media = dataclasses.replace(media, local_path=wav_path)

                    cost_usd = estimate_assemblyai_cost(
                        duration_seconds, diarize=not no_speakers
                    )
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

                # Provider call (PreparedMedia path only — captions skip this).
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
                    # User passed --title: collapse whitespace for filename.
                    # YAML title preserves the original (display_title).
                    stem = title_to_stem(display_title)
                elif media.title is not None:
                    # Source-resolved title (LocalSource: file stem;
                    # DriveSource: auto-resolved from Content-Disposition,
                    # already validated in the source layer). Route
                    # through title_to_stem so both the --title path and
                    # the source-resolved path produce the same on-disk
                    # filename shape ("Session 17" → Session-17), closing
                    # the convergence gap flagged by the ultrareview of
                    # PR #19's Drive-auto title resolution.
                    #
                    # NOTE: cannot use ``media.local_path.stem`` here:
                    # after the C1 dataclasses.replace swap, local_path
                    # points at the workspace WAV (stem ``audio``), not
                    # the source. media.title is the source-stem fallback
                    # LocalSource.prepare populated.
                    stem = title_to_stem(media.title)
                elif isinstance(media, PreparedTranscript):
                    # Captions source with no --title and oembed title
                    # probe returned None (404 / 401 / hostile title /
                    # network failure). Fall back to the video ID stem.
                    # extra['video_id'] is set by YouTubeSource.prepare;
                    # missing key is a producer-side bug (review I5
                    # invariant — let KeyError bubble with traceback
                    # rather than silently writing 'untitled-DATE.md').
                    stem = media.extra["video_id"]
                else:
                    # Drive source with no --title and the CDN title
                    # probe returned None (file no longer publicly
                    # shared, hostile filename rejected by
                    # validate_title, network failure, etc.). Fall back
                    # to the file ID. extra['drive_file_id'] is set by
                    # DriveSource.prepare; missing key is a producer-side
                    # bug, not user input. Let KeyError bubble with
                    # traceback rather than silently writing
                    # 'untitled-DATE.md' (review I5).
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

            if upload_to_drive:
                if upload_folder_id is None:
                    raise RuntimeError(
                        "upload_folder_id is None despite upload_to_drive=True; "
                        "the upload-to-drive fail-fast check should have caught this"
                    )
                # Both error types exit 4 here (transcript already on disk
                # after a paid AssemblyAI call — recovery means re-uploading,
                # not re-running). DestinationError messages already contain
                # "Transcript saved locally at <path>"; AuthError doesn't, so
                # we print the path explicitly. Pre-flight AuthError (before
                # extract) is a separate path that exits 2.
                try:
                    dest = DriveDestination(folder_id=upload_folder_id)
                    drive_url = dest.upload(output, output.name)
                except AuthError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    console.print(f"[yellow]Transcript saved locally at {output}[/yellow]")
                    raise typer.Exit(code=4) from exc
                except DestinationError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=4) from exc
                console.print(f"Uploaded → {drive_url}")
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
    provider: Annotated[str, typer.Argument(help="Provider to authenticate ('google-drive')")],
) -> None:
    """Authenticate with a cloud provider and save credentials."""
    if provider != "google-drive":
        console.print(f"[red]error:[/red] Unknown provider {provider!r}. Supported: 'google-drive'")
        raise typer.Exit(code=2)

    if not settings.google_oauth_configured:
        console.print(
            "[red]error:[/red] Google OAuth credentials not configured.\n"
            "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env\n"
            "(see .env.example for setup instructions)"
        )
        raise typer.Exit(code=2)

    try:
        authenticate_drive(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
        )
    except Exception as exc:
        console.print(f"[red]error:[/red] Drive authentication failed: {exc}")
        raise typer.Exit(code=2) from exc
    console.print("[green]Google Drive authenticated. Token saved.[/green]")


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
