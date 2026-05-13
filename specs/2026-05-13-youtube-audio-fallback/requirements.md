# Requirements — YouTube Source (yt-dlp Audio Fallback)

## Goal

Close the gap Slice 1 left open: when a YouTube URL has no captions
the user can read (creator disabled them, or no track in any language
exists), download the audio with `yt-dlp` and route it through the
existing local-file pipeline — `extract_audio` → AssemblyAI — to
produce the same enriched Markdown + YAML frontmatter Slice 1 emits.

Concretely, the user runs:

```bash
uv run ssm-transcriber transcribe "https://youtu.be/<NO_CAPTIONS_ID>" --budget low
```

and gets `./output/<title>-2026-05-13.md` with AssemblyAI-derived
segments, frontmatter populated, and `source_kind: youtube_audio`
recorded so downstream readers know the transcript came from the
audio-fallback path. Cost is whatever AssemblyAI bills for the
video's duration; the budget gate fires *before* yt-dlp downloads
the audio, so the user can decline cheaply.

This slice completes Phase 2: combined with Slice 1, every viewable
YouTube video the user passes — captioned or not — now produces a
usable transcript. Captioned videos stay free; captionless videos
cost real money but only after explicit consent.

## Non-goals

Each item below is explicitly out of scope for this slice and lands
later:

- **`faster-whisper` provider.** Originally PLAN.md proposed Slice 2
  ship audio fallback + local ASR together. Mid-brainstorm scope
  audit revealed the codebase has no `providers/faster_whisper.py` —
  only `transcription_provider: "faster_whisper"` declared in config
  defaults. Adding a new provider in the same slice as the new source
  would dilute both. faster-whisper moves to a separate slice (call
  it Slice 2b) when there's appetite to land model-download UX,
  device autodetect, and per-call quality tuning together. Today,
  Slice 2's audio fallback routes through AssemblyAI only — the one
  working provider.

- **Age-restricted / member-only / paid-content videos.** yt-dlp can
  download these only with auth cookies. Adding cookie/OAuth handling
  is its own concern (the Drive OAuth slice, #23, is the natural
  home for the broader "private content via auth" surface). Today
  these videos raise `ExtractorError` with an age-restriction or
  authentication message and exit 2 — same UX as Slice 1's
  `AgeRestricted` arm, just routed through the audio path's
  exception matrix instead of the captions library's.

- **Geo-restricted videos.** `yt_dlp.utils.GeoRestrictedError` is its
  own subclass; same "can't fix without infra the slice doesn't
  ship" category as age-restricted. Exit 2 with a clear message
  pointing at the restriction.

- **Playlists and channels.** Slice 1's `_extract_video_id` already
  rejects non-single-video URLs ("must be a single video URL — not
  a playlist or channel"). Slice 2 inherits that — the audio path
  never sees a playlist URL because the parser rejects it before
  source dispatch.

- **YouTube Shorts handling.** Already covered by Slice 1's
  `_PATH_KEYWORDS = ("embed", "shorts", "live")` regex arm
  (`youtube.py:60`) and `test_extract_video_id_youtube_shorts`
  (`test_youtube_source.py:95`). Shorts URLs are valid input today;
  this slice's coverage extends naturally to them via the
  fallback path (Shorts are the most common captionless content,
  so this is where Slice 2 earns most of its keep).

- **Live streams / DVR / premieres.** yt-dlp's behaviour diverges
  significantly for live content (live HLS streams, in-progress
  premieres, ended live streams without DVR archival). Each variant
  has its own failure mode and UX question. We don't ship support;
  yt-dlp's existing `ExtractorError` for these surfaces as an
  exit-2 error. A future slice can investigate if real demand
  surfaces.

- **Audio format or quality flags.** No `--audio-format`,
  `--audio-quality`, or similar CLI surface. yt-dlp's `bestaudio/best`
  format selector is the only path. AssemblyAI accepts any format
  `ffmpeg` can decode (which `extract_audio` already normalises
  to 16 kHz mono WAV). Adding format flags adds CLI surface
  without a concrete user need.

- **`--captions-only` / `--audio-only` flags.** The captions-first /
  audio-fallback ordering is the source's identity (the whole reason
  this is one source class, not two). No user has asked for
  bypassing it. Adding the flag now is over-parameterisation.

- **`--keep-temp` for downloaded audio.** `keep_temp: bool = False`
  is declared in config but not wired up anywhere in the codebase.
  Wiring it up is a separate plumbing fix — not the audio-fallback
  slice's job. Today, downloaded audio is cleaned up with the rest
  of the `RunWorkspace` after the run.

- **Transcript caching for the audio path.** No cache module exists
  in the codebase yet (`cache_dir` / `cache_enabled` settings are
  declared but unwired). Adding a cache infrastructure for either
  the captions path or the audio path is its own slice. Until then,
  every run re-fetches and re-transcribes — the cost is the
  AssemblyAI bill for the audio path, and zero for the captions
  path.

- **Caching the metadata probe response.** Single HTTP request,
  negligible cost — adds complexity for no real saving.

- **Audio fallback as the default on `--budget free`.** AssemblyAI
  costs > 0; `free` budget means "no paid providers." So the
  audio fallback is *implicitly* gated by budget: `free` budget +
  no captions → exit 2 with a budget-aware error message. This is
  policy, not configuration — there's no flag to override it.

## Architecture (locked from brainstorm)

The seven design decisions made during the brainstorm, captured here
so the impl PR has no room to drift:

1. **One class owns both paths.** `YouTubeSource` exposes two
   methods: `prepare()` runs the captions path and raises
   `NoCaptionsAvailable` (a slice-defined exception) on the two
   trigger conditions; `prepare_audio_fallback(workspace)` runs the
   probe + download path. The CLI orchestrates between them so the
   budget gate (which the source must not know about — sources are
   money-agnostic, matching `LocalSource` / `DriveSource`) fires
   between captions failure and yt-dlp probe. Output of either
   method is the existing `PreparedSource` union —
   `PreparedTranscript` from `prepare()`, `PreparedMedia` from
   `prepare_audio_fallback`. The dispatcher (`sources/__init__.py`)
   is unchanged: still hostname-match → `YouTubeSource(uri)`.

2. **Fallback trigger condition is conservative.** Exactly two
   library exceptions flow through to the audio path:
   `TranscriptsDisabled` (creator disabled captions) and
   `NoTranscriptFound` (no track in any language). Every other
   exit-2 exception from the captions library (`VideoUnavailable`,
   `VideoUnplayable`, `InvalidVideoId`, `AgeRestricted`,
   `PoTokenRequired`) and every exit-3 (`IpBlocked`,
   `YouTubeRequestFailed`, etc.) preserves Slice 1's behaviour
   1:1 — same error message, same exit code, no audio attempted.

3. **Probe-first, budget-gate, then download — orchestrated by the
   CLI across three source methods.** The source exposes three
   discrete operations (each one self-contained, source class stays
   money-agnostic). CLI orchestrates the sequence:

     1. `source.prepare()` → runs captions path. Raises
        `NoCaptionsAvailable` on the two trigger exceptions.
     2. CLI catches `NoCaptionsAvailable`:
        - If `--budget` is `free`: emit the budget-aware error
          message → exit 2. **No yt-dlp call at all.** This is
          the pre-flight short-circuit — captionless videos on
          free budget never touch the network beyond the captions
          library round-trip.
        - Otherwise: continue to step 3.
     3. CLI calls `source.probe_audio() → AudioProbe`. Single
        yt-dlp `extract_info(url, download=False)` round-trip;
        returns a slice-local dataclass with the two fields the
        CLI cares about: `duration` (seconds, int) and `title`
        (str).
     4. CLI runs `budget_check` with `cost_usd =
        estimate_assemblyai_cost(probe.duration, diarize=...)` —
        a *real* cost estimate, identical UX to today's local-file
        flow. User confirms (or `-y` skips). Decline → exit 0
        with "Cancelled by user; no charge incurred."
     5. CLI calls `source.download_audio(workspace, probe) →
        PreparedMedia`. yt-dlp downloads the audio to the workspace
        using `bestaudio/best` format. The probe argument
        threads the title forward so we don't re-probe.
     6. Existing pipeline takes over: `extract_audio` canonicalises
        the downloaded file to 16 kHz mono WAV → AssemblyAI →
        `TranscriptResult` → formatter → write → optional Drive
        upload.

   **Title resolution:** the probe's `title` field replaces the
   oembed call for the audio path. Oembed stays the title source
   for the captions path (already shipped, no churn).

   **Why three methods, not one orchestrator inside the source:**
   the budget decision lives in the CLI today (`LocalSource` and
   `DriveSource` don't know about money — `budget_check` is
   called in `cli.py`, not inside source classes). Threading
   budget into a single `prepare()` orchestrator would break the
   "sources are money-agnostic" invariant. Three discrete methods
   each do one thing, and the CLI does the across-method
   orchestration the same way it already does for the
   captions-vs-PreparedMedia branch.

4. **`youtube_audio` source-kind label.** Symmetric pair with
   Slice 1's `youtube_captions`. Both name a specific runtime
   path; the type-design issue #32 wants per-path Literals anyway.
   `SourceKind` Literal becomes `"local" | "google_drive" |
   "youtube_captions" | "youtube_audio"`.

5. **`bestaudio/best` format, no postprocessors.** yt-dlp picks the
   smallest playable audio stream YouTube serves — typically m4a or
   opus — and writes it to the workspace. The existing
   `extract_audio` normalises to 16 kHz mono WAV. One ffmpeg run
   (downsample), not two (no yt-dlp postprocessor). PreparedMedia
   carries the yt-dlp output path; the local-file pipeline takes
   over from there with zero changes.

6. **yt-dlp's built-in retries, not tenacity.** `retries=3`,
   `fragment_retries=3`, `socket_timeout=30` on the `YoutubeDL`
   instance. yt-dlp's retry machinery is protocol-aware (HLS
   fragments, chunked-encoding mid-stream resumes) — wrapping it
   with tenacity would double-retry against a target that's
   already retrying internally. The captions library doesn't
   retry; yt-dlp does. Different libraries, different policies.

7. **Exit-code matrix mirrors Slice 1.** Audio-path exceptions
   map to the same `2 / 3 / 4` matrix Slice 1 established:

   | Condition | Exit | Mirrors Slice 1 |
   |---|---|---|
   | `ExtractorError` (video gone, private, age-restricted, paid) | 2 | `VideoUnavailable` / `AgeRestricted` |
   | `GeoRestrictedError` | 2 | (new "user can't fix without infra" arm) |
   | `DownloadError` after retries exhausted | 3 | `YouTubeRequestFailed` |
   | HTTP 429 / IP block (after retries) | 3 | `IpBlocked` |
   | `PostProcessingError` (ffmpeg failure inside yt-dlp) | 4 | (new I/O arm, same category as `AudioExtractError`) |
   | Disk full / permission (`OSError`) | 4 | matches existing workspace I/O failures |

## Frontmatter contract

The audio-fallback path produces the existing Slice-1 frontmatter
shape with these specific field values:

```yaml
title: <yt-dlp probe.title>
source_uri: https://youtu.be/<video_id>     # canonical short form, NOT file://
source_kind: youtube_audio
duration_seconds: <result.duration_seconds>  # from AssemblyAI's response
language: <result.language>                  # from AssemblyAI
provider: assemblyai
model: universal-3-pro                       # or whatever assemblyai default
# caption_type field is OMITTED entirely (it's captions-arm-only)
diarized: true | false
speakers: <count> | null
assemblyai_job_id: <result.job_id>           # populated, not null
created: 2026-05-13
```

Critical: `source_uri` is the **YouTube URL**, not the workspace
`file://` path. The workspace gets cleaned up after the run; a
`file://` URI to a deleted workspace path is silent rot. The
formatter's `_source_uri` helper grows a `youtube_audio` arm
returning `media.original_uri` (the canonical YouTube short-form
URL Slice 1 already stores).

The body's summary blockquote uses the normal `<provider>/<model>`
shape (`assemblyai/universal-3-pro`) — *not* Slice 1's special-cased
`youtube-captions (auto|manual)` label. The captions special case
stays gated on `kind == "youtube_captions"`.

## User-visible behaviour matrix

For every combination of `--budget` × captions availability:

| Budget | Captions available | Outcome |
|---|---|---|
| `free` | Yes | Captions path; $0 — same as Slice 1 today |
| `free` | No | Exit 2 with "no captions found; audio fallback requires `--budget low+`". No yt-dlp probe, no download. |
| `low` / `best` | Yes | Captions path; $0 — same as Slice 1 today |
| `low` / `best` | No | yt-dlp metadata probe → cost-confirmation prompt (with `-y` to skip) → yt-dlp downloads audio → existing pipeline runs → AssemblyAI bills for the duration |

The Slice 1 `_no_captions_message` becomes budget-aware: the message
text differs between `free` and `low+` budgets so the user gets the
right next-action hint either way. On `low+`, the message is in
practice never seen — the audio fallback fires silently and the
budget gate's cost prompt is the user-visible signal.

## Out-of-band cost signal

The audio path's cost confirmation prompt is the existing
`budget_check`-based flow. No new prompt UX is invented. The
`cost_summary` string passed to `budget_check` calls out that this
is the audio-fallback path (not just "AssemblyAI for a local file")
so the user understands *why* they're being asked to authorise spend
on what looked like a free-by-default YouTube URL.

Verbatim string (specced now so the impl can't drift):

```
Provider: AssemblyAI · YouTube audio fallback — captions unavailable
for this video; transcribing the downloaded audio. Estimated cost
based on probe duration; AssemblyAI's per-minute bill is final.
```

## Reference calls (verbatim)

The CLAUDE.md guardrail is hard: vendor API calls must be copied
from a working call or ctx7 fetch performed within the current PR.
This section is the source of truth for the impl PR — any code
diverging from these shapes must update this section first.

### yt-dlp: import surface and exception types

ctx7 retrieval date: 2026-05-13
Source: `/yt-dlp/yt-dlp` library docs via Context7.

```python
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError
# Additional subclasses available via yt_dlp.utils:
#   GeoRestrictedError, UnavailableVideoError, UnsupportedError,
#   PostProcessingError
```

### yt-dlp: metadata probe (no download)

```python
ydl_opts = {
    "quiet": True,
    "no_warnings": True,
    "format": "bestaudio/best",
    "retries": 3,
    "fragment_retries": 3,
    "socket_timeout": 30,
}

with YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(URL, download=False)
    # info is a dict; key fields the impl reads:
    #   info["title"]    — str, human-readable title (oembed analogue)
    #   info["duration"] — int | float, video length in seconds
    #   info["formats"]  — list of dicts; informational only,
    #                      bestaudio/best already picks
    # Do NOT json.dumps(info) — it contains non-serializable bits.
    # Use ydl.sanitize_info(info) if a serializable copy is needed.
```

### yt-dlp: audio download to workspace

```python
ydl_opts = {
    "quiet": True,
    "no_warnings": True,
    "format": "bestaudio/best",
    "retries": 3,
    "fragment_retries": 3,
    "socket_timeout": 30,
    "outtmpl": str(workspace.path / "audio.%(ext)s"),
    "noplaylist": True,  # defence-in-depth; parser already rejects playlists
}

with YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(URL, download=True)
    # info["requested_downloads"][0]["filepath"] is the on-disk path
    # of the downloaded audio file (with the actual extension yt-dlp
    # chose — m4a, opus, webm, etc.). PreparedMedia.local_path = this.
```

### yt-dlp: exception examples (from ctx7)

```python
try:
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(URL, download=True)
except ExtractorError as e:
    # Video-level errors: unavailable, private, age-restricted, etc.
    # Subclasses: GeoRestrictedError, UnavailableVideoError,
    # UnsupportedError. All caught by ExtractorError base.
    ...
except DownloadError as e:
    # Network-level errors after retries exhausted. Includes
    # post-processing failures wrapped from PostProcessingError.
    ...
```

Note: the docs example uses `'ignoreerrors': True` to suppress
errors. **We do not set this** — the slice depends on errors
propagating so the exit-code matrix can route them.

### youtube-transcript-api: unchanged from Slice 1

The captions-arm calls are unchanged; this slice does not re-fetch
that library's docs. Slice 1's spec is the authoritative reference.
