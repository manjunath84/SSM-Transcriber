"""YouTube captions source — Phase 2 Slice 1.

Pulls existing YouTube captions via ``youtube-transcript-api`` and emits
a finished ``PreparedTranscript`` directly. No audio download, no paid
provider call. Captions cover the common "I want to read what they said"
case at $0; the yt-dlp audio fallback for videos without captions lands
in Slice 2 (issue #21).

The library is an unofficial scraper of YouTube's frontend; we pin a
range and document the trade-off in the spec under "Constraints". The
library ≥1.0 API surface is the binding contract — see the verbatim
reference in
``specs/2026-05-12-youtube-captions-source/requirements.md``
§"Reference calls (verbatim)".
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from transcriber.core.title import validate_title
from transcriber.providers.base import Segment, TranscriptResult
from transcriber.sources.base import (
    PreparedMedia,
    PreparedTranscript,
    SourceInputError,
)

if TYPE_CHECKING:
    from transcriber.core.workspace import RunWorkspace


@dataclass(frozen=True)
class AudioProbe:
    """Result of yt-dlp's metadata-only ``extract_info(download=False)``.

    The two fields the CLI orchestration reads — duration for the cost
    estimate, title to thread forward to ``PreparedMedia.title`` so we
    don't re-probe via oembed on the audio path. ``frozen=True`` mirrors
    ``PreparedMedia`` / ``PreparedTranscript`` and prevents accidental
    mutation between probe and download.

    ``duration > 0`` is a type-level invariant — the cost estimator
    treats negative or zero seconds as "$0", which would silently
    bypass the budget gate. The probe helper raises
    ``ProbeDurationUnknown`` before construction; this guard catches
    future producers that forget. ``title`` is ``None`` when the
    upstream probe returned no usable title (missing key, hostile
    creator-controlled value rejected by ``validate_title``); the
    CLI's filename derivation falls back to ``extra['video_id']``.
    """

    duration: int
    title: str | None

    def __post_init__(self) -> None:
        if self.duration <= 0:
            raise ValueError(
                f"AudioProbe.duration must be > 0, got {self.duration!r}"
            )


class NoCaptionsAvailable(Exception):
    """Raised by ``YouTubeSource.prepare`` when the captions library
    reports captions are unavailable (``TranscriptsDisabled`` /
    ``NoTranscriptFound``).

    The original library exception is preserved in ``__cause__`` so the
    CLI can still distinguish the two reasons when emitting the
    budget-aware no-captions message. All other captions-library
    exceptions (``VideoUnavailable``, ``AgeRestricted``, etc.) propagate
    unchanged.
    """


class ProbeDurationUnknown(Exception):
    """yt-dlp's probe returned ``None`` or a non-positive duration.

    The realistic cause is a live stream or premiere — content without
    a fixed duration. Without duration we can't compute a reliable
    AssemblyAI cost estimate, so the audio fallback exits 2 rather than
    showing the user a fake ``$0.00`` cost prompt.
    """


# yt-dlp options for both probe (extract_info(download=False)) and
# download (extract_info(download=True)). The dict is the verbatim
# reference call captured in
# ``specs/2026-05-13-youtube-audio-fallback/requirements.md``
# ``## Reference calls (verbatim)`` — any value change must update
# the spec first. ``noplaylist`` is defence-in-depth (the URL parser
# already rejects playlist forms; yt-dlp's auto-playlist behaviour for
# some edge URLs would otherwise expand a single video into multiple).
_YDL_OPTS_BASE: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "format": "bestaudio/best",
    "retries": 3,
    "fragment_retries": 3,
    "socket_timeout": 30,
    "noplaylist": True,
}


def _probe_metadata(url: str) -> AudioProbe:
    """yt-dlp metadata round-trip — no download. Returns AudioProbe
    populated from ``info["title"]`` and ``info["duration"]``.

    Raises ``ProbeDurationUnknown`` when the response is missing,
    when ``duration`` is missing/non-numeric/non-positive (live
    streams, premieres, malformed metadata). All other yt-dlp
    exceptions propagate to the CLI for exit-code mapping via
    ``_handle_yt_dlp_exception``.

    yt-dlp is imported locally because the module is large (~50 MB
    in-memory after extraction registry init); deferring keeps the
    captions-only happy path lightweight.
    """
    from yt_dlp import YoutubeDL  # noqa: PLC0415 — deferred-import, see docstring

    with YoutubeDL(_YDL_OPTS_BASE) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        raise ProbeDurationUnknown(url)
    duration = info.get("duration")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise ProbeDurationUnknown(url)
    # probe.title is creator-controlled metadata that the CLI uses as
    # the default filename stem after only whitespace collapsing. Run
    # it through validate_title so a hostile title like ``../outside``
    # or ``subdir/name`` can't redirect the write outside
    # settings.output_dir. Fail-soft to None → CLI falls back to
    # extra['video_id'] (same shape as the oembed probe).
    raw_title = info.get("title")
    title: str | None
    if raw_title:
        try:
            title = validate_title(str(raw_title))
        except ValueError:
            logger.debug(
                "yt-dlp probe: rejected hostile title %r for url=%s",
                raw_title,
                url,
            )
            title = None
    else:
        title = None
    return AudioProbe(duration=int(duration), title=title)


def _download_audio(url: str, workspace: RunWorkspace) -> Path:
    """yt-dlp audio download. Returns the on-disk Path of the
    downloaded artifact (extension picked by yt-dlp via
    ``bestaudio/best`` — could be m4a, opus, webm, etc.).

    yt-dlp exceptions propagate; the CLI maps them via
    ``_handle_yt_dlp_exception``. A response shape we don't recognise
    (post-processing dropped ``requested_downloads``, the list is
    empty, or the first entry has no ``filepath``) surfaces as
    ``DownloadError`` so the same catch + exit-3 + "no charge
    incurred" reassurance fire — a raw ``KeyError`` here would escape
    the CLI's catch tuple and dump a traceback.
    """
    from yt_dlp import YoutubeDL  # noqa: PLC0415 — see _probe_metadata
    from yt_dlp.utils import DownloadError  # noqa: PLC0415

    opts = {
        **_YDL_OPTS_BASE,
        "outtmpl": str(workspace.path("audio.%(ext)s")),
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    requested = (info or {}).get("requested_downloads") or []
    if not requested:
        raise DownloadError(
            f"yt-dlp returned no downloaded file for {url!r}"
        )
    filepath = requested[0].get("filepath")
    if not filepath:
        raise DownloadError(
            f"yt-dlp returned a downloaded entry without a filepath for {url!r}"
        )
    return Path(filepath)

logger = logging.getLogger(__name__)

# Oembed probe — fail-soft GET against YouTube's public title endpoint.
# Mirrors the Drive Slice 2 ``Content-Disposition`` filename-probe
# pattern: one unauthenticated round-trip, parsed defensively, returns
# ``None`` on any failure so the caller falls through to the video ID
# stem. Verified verbatim 2026-05-12 against a real YouTube URL — see
# specs §"Reference calls (verbatim)".
_OEMBED_URL = "https://www.youtube.com/oembed"
_OEMBED_TIMEOUT_SECONDS = 10.0

# YouTube video IDs are exactly 11 chars, URL-safe base64 (A-Z, a-z, 0-9, -, _).
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Path-form keywords whose immediately-following segment is the video ID.
# ``/embed/<ID>``, ``/shorts/<ID>``, ``/live/<ID>`` — all three are
# accepted; ``/watch`` is handled separately because the ID lives in
# the query string, not the path.
_PATH_KEYWORDS = ("embed", "shorts", "live")

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_YOUTU_BE_HOSTS = {"youtu.be"}


def _validate_id(candidate: str) -> str:
    """Return the candidate ID if it matches the 11-char regex, else raise."""
    if not _VIDEO_ID_RE.fullmatch(candidate):
        raise SourceInputError(
            f"could not extract a video ID from the URL: "
            f"{candidate!r} is not a valid YouTube video ID "
            "(expected exactly 11 characters of [A-Za-z0-9_-])."
        )
    return candidate


def _extract_video_id(uri: str) -> str:
    """Extract the 11-char video ID from any of the eight accepted forms.

    Raises ``SourceInputError`` (subclass of ``ValueError`` for back-compat
    with existing ``pytest.raises(ValueError, ...)`` tests) on any
    rejected form — playlist, channel, channel-handle, homepage,
    malformed IDs. The CLI maps this to exit 2.
    """
    parsed = urlparse(uri)
    host = (parsed.hostname or "").lower()

    if host in _YOUTU_BE_HOSTS:
        # ``youtu.be/<ID>`` — path is ``/<ID>``; strip leading slash.
        candidate = parsed.path.lstrip("/")
        return _validate_id(candidate)

    if host in _YOUTUBE_HOSTS:
        path = parsed.path
        if path == "/watch":
            # ``?v=<ID>`` query parameter.
            qs = parse_qs(parsed.query)
            v_values = qs.get("v", [])
            if not v_values:
                raise SourceInputError(
                    f"could not extract a video ID from {uri!r}: "
                    "/watch URL is missing the ?v=<ID> parameter."
                )
            return _validate_id(v_values[0])

        # Path-keyword forms: /embed/<ID>, /shorts/<ID>, /live/<ID>.
        # ``path.split("/")`` on ``/embed/abc`` yields ``["", "embed", "abc"]``.
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in _PATH_KEYWORDS:
            return _validate_id(parts[1])

        # Playlist / channel / homepage / @handle / anything else.
        raise SourceInputError(
            f"could not extract a video ID from {uri!r}: "
            "supply a single video URL (watch?v=..., youtu.be/..., "
            "embed/, shorts/, or live/ form). Playlist, channel, and "
            "channel-handle URLs are not supported."
        )

    raise SourceInputError(
        f"could not extract a video ID from {uri!r}: "
        "expected a YouTube hostname (youtube.com, youtu.be, m.youtube.com)."
    )


def _fetch_oembed_title(video_id: str) -> str | None:
    """Return the YouTube video title via the public oembed endpoint, or
    ``None`` on any failure path.

    No auth required; the endpoint is YouTube's documented title-resolution
    surface. Parallels Drive's ``_fetch_drive_filename`` — one fail-soft
    GET, defended against every error mode (network, non-200, malformed
    JSON, missing key, hostile creator-controlled title).
    """
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        response = requests.get(
            _OEMBED_URL,
            params={"url": watch_url, "format": "json"},
            timeout=_OEMBED_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.debug("oembed probe failed: %s", exc)
        return None

    if response.status_code != 200:
        logger.debug(
            "oembed probe returned %d for video=%s", response.status_code, video_id
        )
        return None

    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        logger.debug("oembed probe: malformed JSON: %s", exc)
        return None

    raw_title = payload.get("title") if isinstance(payload, dict) else None
    if not isinstance(raw_title, str) or not raw_title:
        return None

    # Creator-controlled metadata can carry path-traversal characters or
    # YAML-corrupting control characters; same defence as Drive's filename
    # probe (validation case 46).
    try:
        return validate_title(raw_title)
    except ValueError:
        logger.debug(
            "oembed probe: rejected hostile title %r for video=%s",
            raw_title,
            video_id,
        )
        return None


def _pick_transcript(transcript_list: Any, video_id: str) -> Any:
    """Iterate ``transcript_list``, prefer manually-created over
    auto-generated. Auto-translated tracks are excluded by construction —
    they only appear when we call ``.translate()`` ourselves, which we
    don't.

    Ordering precision (PR #31 comment-analyzer finding):
    - Manual-vs-auto preference is order-independent — we explicitly
      filter on ``is_generated`` and would pick the manual track even
      if the library returned auto first.
    - **Language-within-category IS order-dependent.** We pick the
      first manual track and the first auto track the library yields,
      relying on the library's documented natural order (original
      language first within each category). If the library ever
      changes to user-locale-first iteration this resolver would
      silently switch tracks; a future-debug breadcrumb is the test
      ``test_canonical_source_uri_is_short_form_regardless_of_input``
      which still pins the produced ``video_id`` even when iteration
      order changes.
    """
    manual = None
    auto = None
    for transcript in transcript_list:
        if not transcript.is_generated and manual is None:
            manual = transcript
        elif transcript.is_generated and auto is None:
            auto = transcript
    chosen = manual if manual is not None else auto
    if chosen is None:
        raise NoTranscriptFound(video_id, ["<original language>"], transcript_list)
    return chosen


def _build_transcript_result(fetched: Any) -> TranscriptResult:
    """Map a library ``FetchedTranscript`` to the codebase's
    ``TranscriptResult``.

    Snippet ``start`` and ``duration`` are seconds (float); ``Segment``
    stores integer milliseconds. ``duration_seconds`` is the end of the
    last segment — the Q4b decision: oembed has no duration field
    (verified by real curl 2026-05-12), and last-caption-end is the
    cheapest honest approximation.
    """
    snippets = list(fetched)
    segments = [
        Segment(
            start_ms=int(s.start * 1000),
            end_ms=int((s.start + s.duration) * 1000),
            text=s.text,
            speaker=None,
        )
        for s in snippets
    ]
    duration_seconds = (
        max(s.start + s.duration for s in snippets) if snippets else 0.0
    )
    text = " ".join(s.text for s in snippets)
    return TranscriptResult(
        text=text,
        segments=segments,
        language=fetched.language_code,
        duration_seconds=duration_seconds,
        provider="youtube-captions",
        model=None,
        job_id=None,
    )


# Retry policy — 3 attempts, exponential backoff (1s/2s/4s), retry on
# any ``requests.RequestException`` subclass (covers Timeout,
# ConnectionError, ChunkedEncodingError, TooManyRedirects,
# ContentDecodingError, InvalidURL, etc.). The narrower (Timeout,
# ConnectionError) pool the spec originally listed missed mid-fetch
# transient errors like ChunkedEncodingError, which then surfaced as a
# raw traceback at the CLI — silent-failure-hunter finding on PR #31.
#
# Library-level exceptions (TranscriptsDisabled, NoTranscriptFound,
# VideoUnavailable, IpBlocked, RequestBlocked, AgeRestricted, etc.) are
# deterministic in a single run and propagate immediately — they are
# subclasses of ``CouldNotRetrieveTranscript``, NOT of
# ``RequestException``, so this whitelist does NOT accidentally retry
# them. Plan.md §5.
_RETRYABLE_EXC = (requests.RequestException,)


@retry(
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    before_sleep=before_sleep_log(logger, logging.INFO),
    reraise=True,
)
def _fetch_captions(video_id: str) -> Any:
    """Network-touching captions fetch: list tracks, pick one, fetch
    snippets. Wrapped with tenacity so transient connection errors retry
    without re-running URL parsing or oembed.

    Both ``list()`` and ``fetch()`` can raise transient network errors;
    decorating the whole helper retries the entire fetch atomically.
    """
    ytt_api = YouTubeTranscriptApi()
    transcript_list = ytt_api.list(video_id)
    chosen = _pick_transcript(transcript_list, video_id)
    fetched = chosen.fetch()
    return chosen, fetched


class YouTubeSource:
    """Fetch YouTube captions and emit a ``PreparedTranscript``.

    The captions path produces a finished transcript directly — no audio,
    no provider call, no budget gate. The CLI branches on
    ``isinstance(prepared, PreparedTranscript)`` before reaching the
    budget router.
    """

    @staticmethod
    def prepare(
        uri: str,
        workspace: RunWorkspace,
        *,
        title: str | None = None,
    ) -> PreparedTranscript:
        video_id = _extract_video_id(uri)

        try:
            chosen, fetched = _fetch_captions(video_id)
        except (TranscriptsDisabled, NoTranscriptFound) as exc:
            # Audio-fallback trigger: these two exceptions mean the
            # video plays but has no captions we can use. The CLI
            # decides whether to fall through to yt-dlp audio download
            # based on --budget. All other captions-library exceptions
            # propagate unchanged so the captions exit-code matrix is
            # untouched.
            raise NoCaptionsAvailable(
                f"no captions for {uri!r}: {exc.__class__.__name__}"
            ) from exc

        caption_type = "auto" if chosen.is_generated else "manual"
        logger.info(
            "YouTube captions source: video=%s lang=%s caption_type=%s",
            video_id,
            fetched.language_code,
            caption_type,
        )

        # Title resolution: explicit ``--title`` wins; otherwise probe
        # oembed (fail-soft → None falls through to the video ID stem
        # at the CLI's filename-derivation layer).
        resolved_title = title if title is not None else _fetch_oembed_title(video_id)

        result = _build_transcript_result(fetched)
        return PreparedTranscript(
            kind="youtube_captions",
            original_uri=f"https://youtu.be/{video_id}",
            transcript=result,
            title=resolved_title,
            workspace=workspace,
            extra={"video_id": video_id, "caption_type": caption_type},
        )

    @staticmethod
    def probe_audio(uri: str) -> AudioProbe:
        """yt-dlp metadata round-trip for the audio-fallback path.

        Called by the CLI after ``prepare`` raises ``NoCaptionsAvailable``
        on a ``low+`` budget. Returns duration + title cheaply (single
        HTTP round-trip) so the budget gate can fire with a real cost
        estimate before any audio download happens.
        """
        video_id = _extract_video_id(uri)
        return _probe_metadata(f"https://youtu.be/{video_id}")

    @staticmethod
    def download_audio(
        uri: str,
        workspace: RunWorkspace,
        probe: AudioProbe,
        *,
        title: str | None = None,
    ) -> PreparedMedia:
        """yt-dlp audio download — runs only after the CLI confirmed the
        cost-prompt. Threads the probe-derived title and duration
        forward so downstream stages don't re-probe.

        When the user supplies ``--title``, the CLI passes that
        validated string here so ``PreparedMedia.title`` (used by the
        formatter for the frontmatter + H1) honours it. Without the
        override, the probe title is used — mirrors the captions
        arm's behaviour with oembed.
        """
        video_id = _extract_video_id(uri)
        canonical_url = f"https://youtu.be/{video_id}"
        audio_path = _download_audio(canonical_url, workspace)
        resolved_title = title if title is not None else probe.title
        return PreparedMedia(
            kind="youtube_audio",
            original_uri=canonical_url,
            local_path=audio_path,
            title=resolved_title,
            duration_seconds=float(probe.duration),
            workspace=workspace,
            extra={
                "video_id": video_id,
                "probe_duration": str(probe.duration),
            },
            remote_url=None,
        )
