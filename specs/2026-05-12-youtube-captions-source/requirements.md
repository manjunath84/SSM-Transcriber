# Requirements — YouTube Source (Captions Passthrough)

## Goal

Ship the first YouTube source for SSM-Transcriber: take a YouTube video
the user has the right to view and produce the same enriched Markdown +
YAML frontmatter Slice 1 emits, **using YouTube's own captions** — no
audio download, no ASR call, no paid provider. The single
`youtube-transcript-api` fetch is the only network hop on the happy
path (with a parallel oembed GET for the video title).

Concretely, the user runs:

```bash
uv run ssm-transcriber transcribe "https://youtu.be/<ID>" --budget free
```

and gets `./output/<title>-2026-05-12.md` with manual or auto-generated
captions rendered as segments, frontmatter populated, and `caption_type`
recorded so the user knows whether they got human-written or ASR-derived
text. Cost is **$0** (no paid API call, no audio bandwidth).

This slice exists because YouTube captions cover most "I want to read
what they said" cases for free, and audio-download fallback (yt-dlp +
local ASR) is the heavier path that earns its complexity only when
captions aren't available. Slice 2 (issue #21) ships that fallback.

## Non-goals

Each item below is explicitly out of scope for this slice and lands later:

- **yt-dlp audio download fallback.** Phase 2 Slice 2 (issue #21). When
  captions are missing or disabled, Slice 1 exits with a clear error
  pointing at #21 and a manual workaround; it never silently downloads
  audio and routes to a paid provider.
- **Auto-translated captions.** A video with no original-language track
  but an auto-translated track (YouTube's MT layered on top of YouTube's
  ASR) compounds errors. We exclude this category — the user is better
  served by Slice 2's local ASR on the original audio. We never call
  `transcript.translate(...).fetch()`.
- **`--language` flag override on caption sources.** Today's `--language`
  flag is an ASR language *override* (Phase 1 / Slice 1 semantics — feeds
  AssemblyAI's `language_code`). For captions sources, transcription is
  already done — the language is whatever the picked track is in. The
  flag is silently ignored with an INFO log; honoring it would either
  reopen the auto-translated edge case or fail unhelpfully when the
  requested language has no track. A future slice can add a
  `--caption-language` flag if real demand surfaces.
- **Multi-track selection UI.** No `--list-captions` command. The
  resolver picks one track deterministically (manual original → auto
  original).
- **Caching of fetched captions.** F3's cache key is shaped for audio
  hashes; caption fetches are fast and free, so the value/complexity
  trade-off doesn't pay. Same posture as Drive Slice 2.
- **Cost pre-estimation.** Cost is $0 by construction; no estimate is
  needed and no confirmation prompt fires.
- **Channel / playlist / live URLs as iteration entry points.** A
  `youtube.com/live/<ID>` URL is accepted as a single video (live
  streams are eventually captioned post-broadcast); playlist and
  channel URLs are rejected at dispatch with a clear "supply a single
  video URL" message.
- **Gemini / OpenAI / Hugging Face as captions backends.** Phase 5
  (issue #24).
- **Drive Slice 3 (OAuth + private files).** Unrelated.

## Scenarios / user flows

1. **Happy path — manual captions.** User runs
   `uv run ssm-transcriber transcribe "https://youtu.be/<ID>"` against
   a video with a manually-uploaded English caption track. Tool
   resolves the video ID, fetches the caption track, then
   (synchronously, per the F1 sync-only constraint below) fetches the
   oembed title, writes `./output/<oembed-title>-2026-05-12.md` with
   frontmatter `caption_type: manual`. Exit `0`.
2. **Happy path — auto-generated captions.** Same flow against a video
   with no manual track but an auto-generated track. Tool picks the
   auto track, frontmatter shows `caption_type: auto`. Exit `0`.
3. **Happy path — `--title` override.** User passes
   `--title "Session 17"`. Title overrides oembed; output filename and
   frontmatter `title` use the user's value.
4. **Happy path — oembed fails (private/age-restricted but captions
   public).** The oembed endpoint returns 401/403/404 but
   `youtube-transcript-api` still fetches captions. Title falls back
   to the video ID stem; exit `0` — oembed failure NEVER blocks the
   captions path.
5. **No captions available.** User runs against a video where the
   creator has disabled captions OR no auto-generated track exists.
   Exit `2` with the documented message pointing at issue #21 and a
   yt-dlp workaround.
6. **Video unavailable / private / deleted.** Exit `2` with the
   library's `VideoUnavailable` / `VideoUnplayable` message
   surfaced to the user.
7. **Age-restricted video.** Exit `2` with a message explaining that
   age-restricted videos require authentication the library doesn't
   support; Slice 2's yt-dlp fallback (which can authenticate)
   won't help either without browser cookies.
8. **Invalid video ID / unsupported URL form.** User pastes a
   non-video URL like `youtube.com/@channel` or a playlist URL like
   `youtube.com/playlist?list=...`. Exit `2` with the documented
   "supply a single video URL" message.
9. **YouTube returns unexpected response (scraper drift).** Library
   raises a `CouldNotRetrieveTranscript` subclass our error matrix
   doesn't recognise, or `IpBlocked` / `RequestBlocked`. After
   tenacity retries on network-layer errors, exit `3` with the
   pinned library version and a hint that the library may need
   upgrade.
10. **`--budget free`.** Allowed — captions path is $0 and skips the
    budget router entirely. No confirmation prompt fires. The
    Drive-vs-captions asymmetry under `--budget free` is documented
    (Drive needs AssemblyAI → rejected; captions need no provider →
    allowed).
11. **`--language` flag passed.** Silently ignored on captions sources
    with an INFO log: "captions source: --language ignored, returned
    track is <lang>".
12. **User Ctrl-C during fetch.** Workspace cleanup runs via F5; no
    artifacts left behind.

## Constraints and decisions

### From the constitution (binding)

Per `specs/tech-stack.md`, `docs/PLAN.md` F1–F8, and `CLAUDE.md`:

- **Sync only.** No `async def` introduced. `youtube-transcript-api`
  is synchronous; oembed GET runs synchronously after the captions
  fetch returns (no parallel fetch — keeps the call graph simple,
  oembed is sub-second).
- **Config boundary.** `from transcriber.config import settings`
  outside `config.py`. No new env-var reads.
- **No `print()` in library code.** `logger.info` for
  caption-track choice, language, video ID, oembed result; `rich`
  used only at the CLI layer.
- **Two-gate spend (F4).** Bypassed on captions path — the CLI
  branches on `isinstance(prepared, PreparedTranscript)` *before*
  the budget router runs. Gate 1 / Gate 2 N/A (no provider, no key,
  no cost). The router itself is unchanged.
- **Atomic write (F5).** Output goes to `<dest>/<output>.tmp` →
  `os.replace()`, in the destination directory. Same path as Slice 1
  / Drive Slice 2; nothing source-specific.
- **`RunWorkspace` (F5).** Created per CLI invocation even though no
  audio is extracted; keeps lifecycle invariant. The captions JSON
  and oembed response live in memory only, never written to the
  workspace.
- **tenacity retry.** New retry decorator on the
  `youtube-transcript-api` call. Policy mirrors `providers/assemblyai`:
  3 attempts, exponential backoff (1s → 2s → 4s),
  **retry on network-layer exceptions only**
  (`requests.exceptions.ConnectionError`, `Timeout`). Never retry on
  any `CouldNotRetrieveTranscript` subclass — those are deterministic
  in a single run (the IP doesn't unblock in 4 seconds, captions
  don't appear in 4 seconds).
- **Vendor API calls — verbatim copy.** Per the CLAUDE.md guardrail
  added in PR #13, the `youtube-transcript-api` API surface and the
  YouTube oembed response are copied byte-for-byte from §"Reference
  calls (verbatim)" below (ctx7-fetched and curl-verified
  2026-05-12). Never paraphrase from memory.
- **HTTP mocks must use body-shape matchers** for code paths that
  construct the outbound request body. `youtube-transcript-api`
  builds its own requests internally — our code does not construct
  the body, so the `json_params_matcher` rule does not apply to its
  calls (we mock at the library API level instead, see plan §Tests).
  The rule **does** apply to our oembed GET: the `responses` mock
  asserts the exact URL + query parameters we construct.

### Feature-specific decisions (from this session's brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Caption types accepted | **Manual + auto-generated.** Auto-translated explicitly excluded. | Manual is best quality, auto is acceptable. Auto-translated layers MT errors on top of ASR errors — worse than just running local ASR (Slice 2). Excluding it is one fewer branch to maintain. |
| Track selection policy | **Original-language-first**: iterate `transcript_list`, prefer manual, fall back to auto. Never call `.translate()`. | The 99% case is "transcribe this video in whatever language it's in." `ytt_api.fetch(video_id)` without args defaults to English (per library docs), which is wrong for non-English videos. Iterating the list ourselves is the explicit, correct path. |
| `--language` semantics on captions | **Silently ignored with INFO log.** | The flag is an ASR-language *override* in Slice 1's semantics. Captions are pre-transcribed. Honoring the flag opens the auto-translated edge case (already excluded) or fails unhelpfully. A future slice can add `--caption-language` if needed. |
| Title source | **YouTube oembed** (no auth, public) → fail-soft → video ID stem. `--title` flag overrides everything. | Public oembed endpoint returns the video title without OAuth or scope-broadening. Parallels Drive Slice 2's `Content-Disposition` filename probe. Fail-soft on every error path (401/403/404/network) keeps the captions path robust. |
| Duration source | **End of last caption segment** (`max(snippet.start + snippet.duration)`). | Captions are speech-only; the last segment's end approximates speech duration. Free, no extra fetch. Slight under-count if the video ends with uncaptioned silence/music — documented as an acceptable approximation. oembed does NOT return duration (verified by real curl 2026-05-12). |
| `caption_type` location | **`PreparedTranscript.extra["caption_type"]` (literal "manual"\|"auto").** | Keeps `PreparedTranscript` source-agnostic — future caption-like sources (Otter export, NotebookLM saved transcripts) won't carry a meaningless field. Formatter checks `media.kind == "youtube_captions"` and inserts the frontmatter field from `extra`. |
| Source contract — `PreparedSource` Protocol | **New `PreparedSource` Protocol with `PreparedMedia` and new `PreparedTranscript` sibling.** Each source's `prepare()` method returns `PreparedSource` (`PreparedMedia` from Local / Drive; `PreparedTranscript` from YouTube). `resolve_source()` keeps its existing "return the source class" shape — the only change is widening its return-type union to include `type[YouTubeSource]`, so the existing CLI call site `source_cls = resolve_source(uri); source_cls.prepare(...)` continues to work unchanged for Local and Drive. | F2 has been extended additively twice (Drive added `remote_url`); a third extension to `PreparedMedia` for "transcript is already done" would push the dataclass to a three-mode tagged union with a dishonest name ("media" carrying a transcript). The Protocol + sibling pattern is the cleaner refactor; this slice pays the one-time cost now rather than waiting for a fourth source type. Provider stays typed on `PreparedMedia` — `mypy` enforces that the captions path never reaches a provider. |
| `TranscriptResult` extensions | Add **`provider: str`** (was hardcoded `"assemblyai"` in the formatter). Make **`model: str \| None`** (None for captions — YouTube doesn't expose the ASR model behind auto-captions). Make **`job_id: str \| None`** (None for captions — there's no remote job). | Formatter currently hardcodes `provider: assemblyai` and `assemblyai_job_id` rendering. Generalizing to read from the result is a one-line formatter change + 3 dataclass field changes — earns its keep for any future provider, not just captions. Field-name `assemblyai_job_id` in the frontmatter stays for downstream-consumer schema stability; the *content* renders `null` when not from AssemblyAI. Phase 5 generalizes the field name. |
| `SourceKind` literal | Add **`"youtube_captions"`** (tight). | Keeps the existing `"youtube"` literal reserved for Slice 2's yt-dlp+ASR path. Downstream tooling can discriminate "this came from captions" vs "this came from local ASR on YouTube audio." |
| Frontmatter `caption_type` field placement | Inserted between `model` and `diarized`, only when `source_kind == "youtube_captions"`. Omitted (not `null`) for other sources. | Additive schema change. Existing downstream parsers see no missing-required-field; new consumers can opt in. |
| Source dispatch — YouTube hostnames | Match on hostname: `youtube.com`, `www.youtube.com`, `m.youtube.com`, `youtu.be`. | F2's hostname-match rule. Same approach as Drive. Reject-not-swallow stays at the catch-all `://` arm. |
| URL forms accepted | The eight forms documented in §"Reference calls (verbatim)" below. All extract to the same 11-char video ID. | Covers desktop watch, mobile, short link, embed, shorts, live. Playlist and channel URLs are explicitly rejected. |
| Exit codes | Same matrix as Slice 1 / Drive Slice 2. `0` happy / declined; `2` config / user input (no captions, invalid URL, video unavailable, age-restricted); `3` provider-side (network/retry exhaustion, unexpected library exception); `4` local output write failure. | No new code matrix. |
| ToS / scraper posture | `youtube-transcript-api` reverse-engineers YouTube's frontend; widely used (~10K stars). For single-user CLI free-tier use on videos the user is allowed to view, the risk is acceptable. Documented in this constraints section so future readers see the trade-off. | Honest acknowledgement, not a guardrail breach. |
| Caching | **No cache.** F3 deferred (same as Drive Slice 2). | Caption fetch is fast + free; F3's cache key is shaped for audio hashes and doesn't map to `(video_id, caption_type)`. Adding a second cache shape is complexity without payoff. Re-running `transcribe` on a video almost always means "the user wants fresh output." |

## Reference calls (verbatim)

> **Required per PR #13's guardrail.** The implementation copies these
> calls byte-for-byte; never paraphrase from memory.

### `youtube-transcript-api` — current API surface

**Source:** Context7 docs fetch against `/jdepoix/youtube-transcript-api`.
**Retrieval date:** 2026-05-12
**Library docs:** https://github.com/jdepoix/youtube-transcript-api

The library underwent a major API rewrite around v1.0 (static methods →
instance methods, `get_transcript` → `fetch`). The implementation must
target the >=1.0 API only. Pin range: **filled at impl time** after
verifying current PyPI latest; expected shape `youtube-transcript-api>=1.0,<2.0`.

#### Listing and filtering transcripts

```python
from youtube_transcript_api import YouTubeTranscriptApi

ytt_api = YouTubeTranscriptApi()

# List all available transcripts
transcript_list = ytt_api.list("dQw4w9WgXcQ")

# Iterate over all available transcripts — metadata properties
for transcript in transcript_list:
    print(f"Language: {transcript.language} ({transcript.language_code})")
    print(f"  Auto-generated: {transcript.is_generated}")
    print(f"  Translatable: {transcript.is_translatable}")

# Find a manually-created transcript in a language priority
manual = transcript_list.find_manually_created_transcript(['en'])

# Find an auto-generated transcript
generated = transcript_list.find_generated_transcript(['en'])

# Fetch the actual data
fetched = manual.fetch()
```

Iteration order of `transcript_list` is the API's natural order (manual
tracks first; within each category, the original language is typically
first). Our resolver explicitly filters on `is_generated`, so
**manual-vs-auto preference is order-independent**. The
**language-within-category pick is order-dependent**, however — we
take the first manual track and the first auto track the library
yields, which relies on the library's documented "original-language
first" natural order. If a library upgrade ever switches to
user-locale-first iteration, this resolver must change in lockstep
(no language-aware filter).

#### Fetching and consuming a transcript

```python
from youtube_transcript_api import YouTubeTranscriptApi

ytt_api = YouTubeTranscriptApi()
transcript = ytt_api.fetch("dQw4w9WgXcQ")

# Iterate snippets
for snippet in transcript:
    print(f"[{snippet.start:.2f}s] {snippet.text}")

# Metadata on the FetchedTranscript
print(f"Video ID: {transcript.video_id}")
print(f"Language: {transcript.language} ({transcript.language_code})")
print(f"Auto-generated: {transcript.is_generated}")
print(f"Total snippets: {len(transcript)}")

# Convert to raw data (list of dicts)
raw_data = transcript.to_raw_data()  # [{"text": ..., "start": ..., "duration": ...}, ...]
```

**Snippet attributes used by the implementation:**
- `snippet.start: float` — start time in seconds
- `snippet.duration: float` — duration in seconds
- `snippet.text: str` — caption text

Verified against `youtube_transcript_api._transcripts.FetchedTranscriptSnippet`
on 2026-05-13: the constructor signature is `(text: str, start: float,
duration: float)`. No `to_raw_data()` fallback is needed; the
implementation accesses these as instance attributes directly.

**Important:** `ytt_api.fetch(video_id)` with no `languages=[]` arg
**defaults to English**, not original language. Our resolver MUST
iterate `transcript_list` and pick a track explicitly. Calling
`fetch()` without a language list will return the wrong track for
non-English videos.

#### Exception classes (complete hierarchy used by the error matrix)

```python
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    VideoUnplayable,
    IpBlocked,
    RequestBlocked,
    InvalidVideoId,
    AgeRestricted,
    NotTranslatable,
    TranslationLanguageNotAvailable,
    CouldNotRetrieveTranscript,  # base class
)
```

Mapping to exit codes (see validation.md for full matrix):

| Exception | CLI exit | Notes |
|---|---|---|
| `TranscriptsDisabled` | 2 | Creator turned off captions |
| `NoTranscriptFound` | 2 | No track in the iteration matched our manual-then-auto filter |
| `VideoUnavailable` | 2 | Video gone / private |
| `VideoUnplayable` | 2 | Surface `.reason` |
| `InvalidVideoId` | 2 | URL parsed but library rejected the ID |
| `AgeRestricted` | 2 | Auth-only; Slice 2 won't help without browser cookies |
| `IpBlocked` / `RequestBlocked` | 3 | IP-level block; retry won't help in a single run |
| `NotTranslatable` / `TranslationLanguageNotAvailable` | should be unreachable (we never call `.translate()`) — if seen, treat as `CouldNotRetrieveTranscript` |
| `CouldNotRetrieveTranscript` (catch-all) | 3 | Unexpected — message names the pinned library version |

### YouTube oembed — public title endpoint

**Source:** real `curl` against the public oembed endpoint
(2026-05-12).
**Retrieval date:** 2026-05-12
**Public docs:** https://oembed.com/ + YouTube's oembed provider

Request:

```bash
curl "https://www.youtube.com/oembed?url=https%3A//www.youtube.com/watch%3Fv%3DdQw4w9WgXcQ&format=json"
```

Response (verbatim — pinned in the unit test):

```json
{
  "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)",
  "author_name": "Rick Astley",
  "author_url": "https://www.youtube.com/@RickAstleyYT",
  "type": "video",
  "height": 113,
  "width": 200,
  "version": "1.0",
  "provider_name": "YouTube",
  "provider_url": "https://www.youtube.com/",
  "thumbnail_height": 360,
  "thumbnail_width": 480,
  "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
  "html": "<iframe ... title=\"Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)\"></iframe>"
}
```

**Fields the implementation uses:** only `title`. All other fields are
discarded.

**Notably absent:** `duration` is NOT in the oembed response. Confirms
the Q4b decision to derive `duration_seconds` from the last caption
segment's end.

**Failure modes (fail-soft on every path):**
- 401 / 403 (age-restricted, region-locked, or `noembed` setting): no
  `title` available → fall through to video ID stem.
- 404 (video deleted between captions-fetch and oembed): treat same as
  401 — captions fetch already succeeded, don't fail the run.
- Network error / DNS / timeout: 10-second timeout, fall through.
- Malformed JSON: fall through.
- The implementation logs at `DEBUG` for any of these (not `WARNING` —
  oembed failure is a normal outcome on a non-trivial fraction of
  videos, not a problem the user can fix).

### YouTube URL forms the parser must accept

All eight forms below round-trip to the same 11-character video ID
`[A-Za-z0-9_-]{11}`:

```text
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42
https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234&index=2
https://youtube.com/watch?v=dQw4w9WgXcQ
https://m.youtube.com/watch?v=dQw4w9WgXcQ
https://youtu.be/dQw4w9WgXcQ
https://youtu.be/dQw4w9WgXcQ?t=42
https://www.youtube.com/embed/dQw4w9WgXcQ
https://www.youtube.com/shorts/dQw4w9WgXcQ
https://www.youtube.com/live/dQw4w9WgXcQ
```

Extraction rules:
- `youtu.be/<ID>` → ID is `path[1:]` (strip leading `/`).
- `youtube.com/watch` → ID is the `v=` query parameter.
- `youtube.com/embed/<ID>`, `youtube.com/shorts/<ID>`,
  `youtube.com/live/<ID>` → ID is `path` segment after the keyword.

URL forms that MUST be rejected (exit 2, "supply a single video URL"):

```text
https://www.youtube.com/playlist?list=PL...           # playlist
https://www.youtube.com/channel/UC...                  # channel
https://www.youtube.com/@channel-name                  # channel handle
https://www.youtube.com/                               # YouTube homepage
```

Validation: extracted IDs must match `^[A-Za-z0-9_-]{11}$`. Anything
else is exit 2 with a clear "could not extract a video ID from `<uri>`"
message.

## Output contracts

The markdown frontmatter for YouTube captions sources uses the existing
Slice 1 / Drive Slice 2 schema **plus** one new optional field:

```yaml
title: <oembed title, or --title override, or video ID stem>
source_uri: https://youtu.be/<VIDEO_ID>      # canonical short form
source_kind: youtube_captions
duration_seconds: <last caption segment end, 1 decimal place>
language: <ISO code from the chosen caption track>
provider: youtube-captions
model: null                                   # honest — YouTube doesn't expose this
caption_type: manual | auto                   # NEW — only when source_kind == youtube_captions
diarized: false                               # captions never have speaker labels
speakers: null
assemblyai_job_id: null                       # kept for cross-source schema shape
created: <YYYY-MM-DD>
```

**Field rules specific to captions:**
- `source_uri`: canonical form `https://youtu.be/<ID>` regardless of
  which URL form the user passed. Round-trippable in a browser; matches
  the way YouTube itself surfaces share links.
- `provider`: literal `youtube-captions`.
- `model`: literal `null` (frontmatter renders the YAML null).
- `caption_type`: literal `manual` or `auto`. **Field is omitted
  entirely on non-captions sources** (additive schema change).
- `assemblyai_job_id`: literal `null` since no AssemblyAI call was
  made. Field stays in the schema for downstream-parser stability;
  Phase 5 may rename to `provider_job_id`.

**Body of the markdown:**
- Same shape as Slice 1: `# <title>`, summary blockquote, `## Transcript`.
- Summary blockquote drops the `assemblyai/<model>` reference and
  shows `youtube-captions (<caption_type>)` instead.
- Segments rendered with `[mm:ss]` timestamps (no speaker prefix —
  captions have no speakers).

## F-contract status

| Contract | Status in this slice | Notes |
|---|---|---|
| F1 — sync model | implemented | No `async def` introduced. |
| F2 — `PreparedMedia` | **extended via Protocol**: new `PreparedSource` Protocol, existing `PreparedMedia` unchanged, new `PreparedTranscript` sibling dataclass. `resolve_source` widens its return signature accordingly. Backward-compatible for `LocalSource` and `DriveSource` (no field changes to `PreparedMedia`). |
| F3 — versioned cache | **deferred** | Same posture as Drive Slice 2; captions are fast + free, no value in caching, F3's audio-hash key doesn't apply. |
| F4 — two-gate spend | **bypassed on captions path** | CLI branches on `isinstance(prepared, PreparedTranscript)` *before* the budget router. The router itself is unchanged. Drive's gate path stays in place. |
| F5 — `RunWorkspace` | implemented | Workspace still created per run for lifecycle consistency, even when no audio file is extracted. |
| F6 — model preflight | N/A | No ASR, no model download. |
| F7 — fixtures | new mocks: caption-list JSON (manual + auto cases), single-caption-track fixture, oembed response fixture, error-path fixtures. No real YouTube hits in CI. One manual-runbook scenario with a real public video. |
| F8 — logging | implemented | INFO log at start: video ID, chosen track's language/caption_type, oembed result (or fail-soft fallback). DEBUG log for oembed failures. |

## Dependencies added

Runtime: **`youtube-transcript-api`** (>=1.0,<2.0; exact bound pinned at
impl time after verifying current PyPI latest as of 2026-05-12).

Dev: **none.** `requests` already in the runtime stack (used by
`google_drive.py` and the existing test mocks). The oembed GET uses
`requests` for consistency with `google_drive.py`'s
`_fetch_drive_filename` pattern. `responses` already in test deps.

`.env.example`: **no change.** No new env vars.
