# Plan — YouTube Source (yt-dlp Audio Fallback)

## 1. `SourceKind` extension

`src/transcriber/sources/base.py` — extend the `SourceKind` Literal:

```python
SourceKind = Literal[
    "local",
    "google_drive",
    "youtube_captions",
    "youtube_audio",   # NEW — Slice 2
]
```

No new dataclass introduced. The audio-fallback path produces the
existing `PreparedMedia` (with `local_path` set to the yt-dlp output
path); only the `kind` value is new.

## 2. `YouTubeSource` — three methods (final shape)

`src/transcriber/sources/youtube.py` — restructure the source to
expose three discrete operations the CLI orchestrates between:

```python
@dataclass(frozen=True)
class AudioProbe:
    """Result of yt-dlp metadata probe — slice-local."""
    duration: int       # seconds, from info["duration"]
    title: str          # from info["title"]


class NoCaptionsAvailable(Exception):
    """Raised by prepare() when captions trigger fallback (the two
    trigger exceptions: TranscriptsDisabled, NoTranscriptFound).

    Carries the original library exception in __cause__ so the CLI
    can preserve the chain for error messages."""


class YouTubeSource:
    def prepare(self, workspace: RunWorkspace) -> PreparedTranscript:
        """Captions path. Raises NoCaptionsAvailable on the two trigger
        exceptions; all other captions-library exceptions propagate
        with Slice 1's existing exit-code semantics."""
        ...

    def probe_audio(self) -> AudioProbe:
        """Metadata-only yt-dlp call. No download. Cheap (single HTTP
        round-trip). Returns AudioProbe for the CLI to compute cost
        and decide on the budget gate."""
        ...

    def download_audio(
        self, workspace: RunWorkspace, probe: AudioProbe
    ) -> PreparedMedia:
        """Download audio to workspace using bestaudio/best. Returns
        PreparedMedia(kind='youtube_audio', local_path=<downloaded>,
        title=probe.title, extra={'video_id': ..., 'probe_duration':
        probe.duration})."""
        ...
```

Captions-library trigger exceptions (`TranscriptsDisabled`,
`NoTranscriptFound`) wrap into `NoCaptionsAvailable`; all others
(`VideoUnavailable`, `VideoUnplayable`, `InvalidVideoId`,
`AgeRestricted`, `PoTokenRequired`, network-family) propagate with
Slice 1's existing exit-code semantics unchanged.

## 3. yt-dlp helpers — module-level, shared by both audio methods

`src/transcriber/sources/youtube.py` — add module-level constants and
helpers. Both `probe_audio` and `download_audio` use the same base
options:

```python
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
    """Single extract_info(download=False) round-trip.

    Returns AudioProbe; propagates yt-dlp exceptions for the CLI
    to map to exit codes via _handle_yt_dlp_exception (§5c).
    """
    from yt_dlp import YoutubeDL  # local import — heavy module
    with YoutubeDL(_YDL_OPTS_BASE) as ydl:
        info = ydl.extract_info(url, download=False)
    duration = info.get("duration")
    title = info.get("title")
    if not duration or duration <= 0:
        raise ProbeDurationUnknown(url)
    if not title:
        title = ""  # CLI/formatter fall back to video_id
    return AudioProbe(duration=int(duration), title=str(title))


def _download_audio(url: str, workspace: RunWorkspace) -> Path:
    """Download audio to workspace; return the on-disk Path."""
    from yt_dlp import YoutubeDL
    opts = {
        **_YDL_OPTS_BASE,
        "outtmpl": str(workspace.path / "audio.%(ext)s"),
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return Path(info["requested_downloads"][0]["filepath"])


class ProbeDurationUnknown(Exception):
    """Probe returned a missing or non-positive duration — usually
    means the video is a live stream or premiere. We can't compute
    a reliable cost estimate without duration, so we exit 2 with
    a clear message rather than running the prompt with a fake $0
    estimate (validation.md edge cases)."""
```

Local imports for `yt_dlp` because the module is large (~50 MB
in-memory after extraction-registry init); deferring lets the
captions-only happy path stay lightweight (only impacts users who
fall through to the audio path, which is the slower path anyway).

The source class methods are thin wrappers over these helpers:

```python
def probe_audio(self) -> AudioProbe:
    return _probe_metadata(self._canonical_url)

def download_audio(
    self, workspace: RunWorkspace, probe: AudioProbe
) -> PreparedMedia:
    audio_path = _download_audio(self._canonical_url, workspace)
    # PreparedMedia field order matches src/transcriber/sources/base.py
    # (kind, original_uri, local_path, title, duration_seconds,
    # workspace, extra, remote_url). duration_seconds is set from the
    # probe so downstream stages don't need to dig into extra; extra is
    # typed dict[str, str] so probe_duration is stringified there for
    # the rare consumer that wants the raw probe value vs ffprobe value.
    return PreparedMedia(
        kind="youtube_audio",
        original_uri=self._canonical_url,
        local_path=audio_path,
        title=probe.title,
        duration_seconds=float(probe.duration),
        workspace=workspace,
        extra={
            "video_id": self._video_id,
            "probe_duration": str(probe.duration),
        },
        remote_url=None,
    )
```

## 4. CLI wiring — orchestration + budget gate + exception matrix

`src/transcriber/cli.py` — extend the transcribe command:

### 4a. Replace `_no_captions_message` with budget-aware variant

Current Slice 1 message points at issue #21. Post-Slice-2:

```python
def _no_captions_message(uri: str, budget: str) -> str:
    if budget == "free":
        return (
            f"no captions found for {uri}, and audio fallback "
            "requires `--budget low` or higher. Re-run with "
            "`--budget low` to enable audio fallback (AssemblyAI; "
            "you'll be prompted to confirm the estimated cost)."
        )
    # On low+ budget, audio fallback fires silently — this message
    # is rendered only on free budget. Keep the function arity for
    # symmetry with the captions arm's call sites.
    raise RuntimeError(
        "_no_captions_message called on non-free budget — caller bug"
    )
```

### 4b. Catch `NoCaptionsAvailable` and run the three-step fallback

```python
try:
    media = source.prepare(workspace)
except NoCaptionsAvailable as exc:
    if budget.value == "free":
        console.print(
            f"[red]error:[/red] {_no_captions_message(uri, 'free')}"
        )
        raise typer.Exit(code=2) from exc
    # Low/best budget: probe → budget gate → download.
    try:
        probe = source.probe_audio()
    except (ExtractorError, DownloadError, ProbeDurationUnknown) as exc:
        code, message = _handle_yt_dlp_exception(exc, uri)
        console.print(f"[red]error:[/red] {message}")
        raise typer.Exit(code=code) from exc

    cost_usd = estimate_assemblyai_cost(probe.duration, diarize=not no_speakers)
    try:
        proceed = budget_check(
            provider_name="AssemblyAI",
            budget=budget.value,
            key_configured=settings.assemblyai_configured,
            cost_usd=cost_usd,
            yes=yes,
            prompt=_confirm_or_decline,
            notify=lambda msg: console.print(msg),
            cost_summary=(
                "Provider: AssemblyAI · YouTube audio fallback — "
                "captions unavailable for this video; transcribing "
                "the downloaded audio. Estimated cost based on probe "
                "duration; AssemblyAI's per-minute bill is final."
            ),
        )
    except BudgetError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    if not proceed:
        console.print("[yellow]Cancelled by user; no charge incurred.[/yellow]")
        raise typer.Exit(code=0)

    # User confirmed — download.
    try:
        media = source.download_audio(workspace, probe)
    except (ExtractorError, DownloadError, PostProcessingError, OSError) as exc:
        code, message = _handle_yt_dlp_exception(exc, uri)
        console.print(
            f"[red]error:[/red] {message} "
            "[dim](no AssemblyAI charge incurred)[/dim]"
        )
        raise typer.Exit(code=code) from exc

# media is now PreparedTranscript (captions) or PreparedMedia (audio).
# The existing PreparedMedia local-path block runs extract_audio +
# AssemblyAI + render + write + optional upload — BUT its inline
# budget_check call must be skipped for kind="youtube_audio" because
# we already gated on probe-derived cost above (see §4e). Without
# that skip the user gets a second prompt after download. The skip
# mirrors how the captions arm skips the budget gate entirely via
# `isinstance(media, PreparedTranscript)` today.
```

The download try/except deliberately appends "no AssemblyAI charge
incurred" — the user authorised spend at the budget gate, but
download-side failure means no provider call was ever made
(`validation.md` edge case "probe succeeds but download fails").

### 4c. Exit-code mapping for yt-dlp exceptions

New helper `_handle_yt_dlp_exception(exc, uri)` that returns
`(exit_code: int, message: str)`. The mapping table:

| Exception type / subclass | Exit | Message snippet |
|---|---|---|
| `GeoRestrictedError` | 2 | "video is geo-restricted in your region; audio fallback requires VPN or a different region" |
| `UnavailableVideoError` | 2 | "video unavailable for download (gone, private, or never existed)" |
| `UnsupportedError` | 2 | "YouTube URL form not supported by yt-dlp" |
| `ExtractorError` (catch-all, age-restriction text in `exc.msg`) | 2 | "video requires authentication (age-restricted, member-only, or paid); audio fallback can't download it without cookies" |
| `ExtractorError` (catch-all, generic) | 2 | "audio extraction failed: <exc.msg>" |
| `DownloadError` (after retries exhausted, network message in `exc.msg`) | 3 | "network failure downloading audio after 3 retries; try again later" |
| `DownloadError` (catch-all) | 3 | "audio download failed: <exc.msg>" |
| `PostProcessingError` | 4 | "ffmpeg failed processing downloaded audio: <exc.msg>" |
| `OSError` | 4 | "local I/O error during audio download: <exc>" |

Add `ProbeDurationUnknown` (from §3) to the matrix as exit 2 with
message "could not determine video duration from yt-dlp probe; the
video may be a live stream, premiere, or otherwise have no
duration metadata. Audio fallback can't show a reliable cost
estimate without it."

Order matters in the `try/except` chain — `GeoRestrictedError` is
a subclass of `ExtractorError`, so catch it before the parent.
Same for `UnavailableVideoError`, `UnsupportedError`. Reference call
example in `requirements.md` `## Reference calls (verbatim)`.

### 4d. Filename fallback arm

`src/transcriber/cli.py` — add `youtube_audio` arm to filename
derivation (currently in the same helper that handles `youtube_captions`):

```python
if media.kind == "youtube_audio":
    # media.title is the probe-returned title (set in
    # download_audio). Fall back to video_id if empty — matches
    # Slice 1's captions-arm contract (review finding I4 mandate:
    # loud over silent).
    return media.title or media.extra["video_id"]
```

### 4e. Bypass the existing pipeline's budget_check for `youtube_audio`

`src/transcriber/cli.py` — the existing local-path block at
`cli.py:489-545` calls `budget_check` after `extract_audio` resolves
duration from the on-disk file. For `kind="youtube_audio"` we've
already gated on the probe-derived duration up in §4b — running it
a second time would either re-prompt the user (interactive) or
unexpectedly cancel non-interactive runs that only provided one
confirmation. Adding the skip:

```python
# Inside the existing PreparedMedia local-path branch, after
# extract_audio + dataclasses.replace canonical-WAV swap, before
# the budget_check call:
if media.kind == "youtube_audio":
    # Audio-fallback path already gated on probe-derived cost
    # (see §4b); skip the redundant budget_check. The probe-vs-
    # ffprobe duration drift (rounding to int seconds in probe vs
    # float in ffprobe) is small enough that we trust the user's
    # earlier authorization. If they diverge by >X% in practice,
    # that's a follow-up signal to add a confirmation-mode prompt
    # — out of scope for this slice.
    proceed = True
else:
    # Existing flow: cost_usd from extract_audio's duration,
    # budget_check fires, user prompted unless -y.
    ...
```

Tests must cover both directions: (i) `kind="youtube_audio"` does
NOT re-prompt; (ii) `kind="local"` does prompt — Slice 1 contract
intact.

## 5. Formatter — `_source_uri` and body summary

`src/transcriber/formatters/markdown.py`:

### 5a. `_source_uri` for `youtube_audio`

Add a fourth arm. The audio path produces a `PreparedMedia` with
`local_path` set (workspace WAV), but the canonical source URI is
the YouTube URL, **not** `file://`. The workspace gets cleaned up;
`file://` to a deleted path is silent rot.

```python
def _source_uri(media: PreparedSource) -> str:
    if media.kind == "local":
        ...  # existing local arm — file://
    if media.kind == "youtube_audio":
        return media.original_uri   # canonical YouTube short-form URL
    return media.original_uri        # google_drive, youtube_captions
```

### 5b. Body summary — no `youtube_audio` special case

The body's summary blockquote currently special-cases
`youtube_captions` (`youtube-captions (manual|auto)`). The
`youtube_audio` arm has nothing special: provider is AssemblyAI,
model is real, the standard `<provider>/<model>` shape is correct.
No code change needed — just confirm in tests that
`assemblyai/universal-3-pro` (or whatever the AAI model is)
renders.

## 6. PLAN.md update

`docs/PLAN.md` lines ~584-606:

- Rewrite Slice 2's description: replace "faster-whisper local ASR"
  with "AssemblyAI via existing local-file pipeline."
- Move the faster-whisper provider work to a new "Phase 2 Slice 2b"
  entry: "Add `faster_whisper` provider + budget routing so the
  default-`free`-budget user has a $0 path for captionless videos.
  Deferred from Slice 2; tracked separately when there's appetite
  to bundle model-download UX + device autodetect + per-call
  quality tuning together."
- Update the verification command to use `--budget low`.

## 7. Tests

`tests/unit/test_youtube_source.py` — extend with:

- `test_prepare_raises_NoCaptionsAvailable_on_TranscriptsDisabled` —
  `prepare()` raises `NoCaptionsAvailable` (wrapping the original
  exception in `__cause__`) on `TranscriptsDisabled`.
- `test_prepare_raises_NoCaptionsAvailable_on_NoTranscriptFound` —
  same, for `NoTranscriptFound`.
- `test_prepare_does_not_wrap_other_captions_errors` — parametrized
  over the 5 non-trigger exit-2 captions exceptions; each one
  propagates **without** `NoCaptionsAvailable` wrapping.
- `test_probe_audio_success` — probe returns `AudioProbe(duration,
  title)` populated from yt-dlp `extract_info` return.
- `test_probe_audio_raises_ProbeDurationUnknown_on_zero_duration` —
  probe returns `duration=None` or `<=0` → raises
  `ProbeDurationUnknown`.
- `test_probe_audio_raises_ExtractorError` — yt-dlp `extract_info`
  raises `ExtractorError`; propagates.
- `test_download_audio_success` — yt-dlp writes to workspace;
  returned `PreparedMedia` has `kind="youtube_audio"`,
  `local_path=<actual on-disk path>`, `title=probe.title`,
  `extra["video_id"]` and `extra["probe_duration"]` set.
- `test_download_audio_raises_DownloadError` — yt-dlp `extract_info`
  raises `DownloadError` after exhausted retries; propagates.
- `test_download_audio_raises_PostProcessingError` — yt-dlp raises
  `PostProcessingError` (ffmpeg failure inside yt-dlp); propagates.
- `test_ydl_opts_match_spec` — assert `_YDL_OPTS_BASE` matches
  `requirements.md` §"Reference calls (verbatim)" byte-for-byte
  (CLAUDE.md vendor-API guardrail per PR #12's lesson).
- `test_ydl_download_opts_include_outtmpl` — confirm
  `_download_audio` augments base opts with the workspace
  `outtmpl` (and only that).

`tests/unit/test_cli.py` — extend with:

- `test_captionless_video_free_budget` — exit 2, no probe attempted.
- `test_captionless_video_low_budget_user_declines_prompt` — probe
  runs, budget prompt fires, user types "n", exit 0, no download.
- `test_captionless_video_low_budget_user_confirms_prompt` — full
  flow end-to-end (probe → confirm → download → mocked AssemblyAI →
  output written).
- `test_captionless_video_low_budget_yes_flag` — `-y` skips the
  prompt; full flow.
- `test_yt_dlp_exception_matrix` — parametrized over the 8+ rows
  in §5c. Each yt-dlp exception subclass produces the expected
  exit code and message.
- `test_captions_then_audio_upload_to_drive` — audio-fallback +
  `--upload-to-drive` happy path (same shared render+write+upload
  block as captions; should already work but locks the contract).

`tests/unit/test_markdown_formatter.py` — extend with:

- `test_render_youtube_audio_frontmatter` — `source_kind:
  youtube_audio`, `source_uri: https://youtu.be/<ID>` (NOT
  `file://`), `provider: assemblyai`, `model` populated, no
  `caption_type` field.
- `test_render_youtube_audio_body_summary` — body shows
  `assemblyai/<model>`, NOT `youtube-captions (...)`.

`tests/manual/end_to_end.md` — add a captionless-video test using a
YouTube Shorts URL (Shorts are the most common captionless content;
finding one is trivial).

## 8. Per-PR teaching artifacts (Phase D)

Following the convention from PRs #15, #17, #30, #31:

- `docs/learn/prs/pr-NNN-youtube-audio-fallback-spec.md` — the
  spec-PR explainer. Mirror PR #30's template: what the slice
  exists for, the design decisions (especially Q1 + Q3), the
  vendor-API guardrail beat (ctx7 fetch for yt-dlp), the
  splits-mid-flight beat (faster-whisper deferred to its own
  slice).
- `docs/learn/prs/pr-NNN-youtube-audio-fallback-impl.md` — the
  impl-PR explainer. Mirror PR #31's template.
- `docs/learn/journey.md` — append a Phase 2 Slice 2 entry.
- `docs/learn/interview-prep.md` — capture the STAR hook (the
  brainstorm-time scope audit that caught faster-whisper drift
  before code was written is a strong interview moment).
- `docs/learn/glossary.md` — add `youtube_audio` source-kind,
  `bestaudio/best` format selector, `extract_info(download=False)`
  metadata probe pattern.
- `docs/learn/python-notes.md` — capture the yt-dlp local-import
  pattern (deferred heavy imports for performance) if it's a new
  pattern to the repo.

## 9. Exit gate

Implementation PR is ready to merge when:

- [ ] All 8 design decisions from the brainstorm visible in the diff
- [ ] Slice 1's `_no_captions_message` updated to budget-aware
- [ ] `extract_audio` pipeline reused unchanged (zero changes to
      `src/transcriber/core/audio.py`)
- [ ] Tests pass: `uv run pytest` (estimate ~30+ new tests)
- [ ] Lints pass: `uv run ruff check src/ tests/` + `uv run mypy src/ tests/`
- [ ] Manual e2e captured in `tests/manual/end_to_end.md` for a real
      captionless YouTube Shorts URL
- [ ] PR description carries `Closes #21`
- [ ] PLAN.md updated (Slice 2 description + new Slice 2b entry)
- [ ] roadmap.md updated (Slice 2 marked done; Slice 2b appears)
- [ ] Per-PR teaching artifacts written (§9)
- [ ] Multi-vendor review pass (Codex / pr-review-toolkit) — same
      convention as PR #31

After merge: board card auto-moves to Done (workflow #1 enabled),
PR #21 auto-closes via `Closes #21`.
