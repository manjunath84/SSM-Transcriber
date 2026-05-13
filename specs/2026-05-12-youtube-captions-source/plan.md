# Plan — YouTube Source (Captions Passthrough)

> Numbered task groups. Each group is a coherent chunk that can be
> implemented and reviewed together. Specific function signatures,
> field names, and other implementation details are deliberately *not*
> specified here — the implementer decides those during the build,
> consistent with `specs/tech-stack.md` conventions and existing
> patterns in `sources/google_drive.py` and `sources/local.py`.

## 1. F2 contract — `PreparedSource` Protocol + `PreparedTranscript`

Update `src/transcriber/sources/base.py`:

- Define a new `PreparedSource` Protocol that captures the shared
  shape: `kind`, `original_uri`, `title`, `workspace`, `extra`. The
  existing `PreparedMedia` already has these fields and conforms
  structurally — no inheritance declaration needed.
- Add a new frozen dataclass `PreparedTranscript` with:
  - `kind: SourceKind`
  - `original_uri: str`
  - `transcript: TranscriptResult`
  - `title: str | None`
  - `workspace: RunWorkspace`
  - `extra: dict[str, str]`
- `PreparedTranscript` has no `__post_init__` invariant beyond what
  the dataclass enforces (it's a single-mode carrier, unlike
  `PreparedMedia`'s exactly-one-of validation).
- Extend `SourceKind`: add `"youtube_captions"`. Keep the existing
  `"youtube"` literal reserved for Slice 2's yt-dlp+ASR path.

Update `src/transcriber/sources/__init__.py`:

- `resolve_source(uri)` return type widens to
  `type[DriveSource] | type[LocalSource] | type[YouTubeSource]`.
- Implementer's call whether to return a `PreparedSource`-typed
  callable instead. Keeping the existing "return the source class"
  pattern is the smaller change.

Tests live in `tests/unit/test_prepared_media.py` (or a new
`test_source_types.py`) — covers the Protocol shape and
`PreparedTranscript` construction.

## 2. `TranscriptResult` generalization

Update `src/transcriber/providers/base.py`:

- `TranscriptResult.provider: str` — **new required field**.
  AssemblyAI provider passes `provider="assemblyai"`. YouTube captions
  source passes `provider="youtube-captions"`.
- `TranscriptResult.model: str | None` — was `str`. None for captions
  (YouTube doesn't expose the ASR model behind auto-captions; honest
  beats made-up).
- `TranscriptResult.job_id: str | None` — was `str`. None for captions
  (no remote job).

Update `src/transcriber/providers/assemblyai.py`:

- Construction sites for `TranscriptResult` now pass
  `provider="assemblyai"`. Existing fields unchanged.

Tests in `tests/unit/test_provider_types.py` extend to cover the new
field and the Optional changes. Existing AssemblyAI tests should
continue to pass — the AssemblyAI path always populates `provider`,
`model`, and `job_id` with strings.

## 3. `YouTubeSource` and URL-form parsing

Add the runtime dependency to `pyproject.toml`:

- `youtube-transcript-api>=1.0,<2.0` — exact upper bound confirmed at
  impl time against the current PyPI latest (retrieval date 2026-05-12).
  The post-1.0 instance-method API is the binding contract; if the
  PyPI latest at impl time is in a different major range, update the
  pin AND the §"Reference calls (verbatim)" section in `requirements.md`
  in the same PR.
- `uv lock` regenerates `uv.lock` accordingly.

New `src/transcriber/sources/youtube.py`:

- `YouTubeSource.prepare(uri, workspace, *, title=None) -> PreparedTranscript`
  (matches the `LocalSource.prepare` / `DriveSource.prepare` shape;
  CLI calls them uniformly).
- URL parsing helper `_extract_video_id(uri)`:
  - Accepts the 10 URL forms documented in `requirements.md`
    §"Reference calls (verbatim)".
  - Returns the 11-char video ID validated against
    `^[A-Za-z0-9_-]{11}$`.
  - Raises `SourceInputError` on unparseable input, on extracted IDs
    that fail the 11-char regex, and on rejected forms (playlist,
    channel, channel-handle, homepage). Folder URLs are not
    applicable. (Reuses the existing `SourceInputError` class
    defined in `sources/base.py` — same exit-2 path as Drive.)
- **Defence-in-depth:** `YouTubeSource.prepare` runs the URL
  validation itself even though `resolve_source` already routes by
  hostname. Tests call `prepare` directly; future programmatic
  callers may bypass dispatch.

Caption resolution helper `_pick_transcript(video_id)`:

- Calls `ytt_api.list(video_id)` (instance-method API, post-1.0).
- Iterates `transcript_list`, preferring `not t.is_generated` (manual)
  over `t.is_generated` (auto). The original-language assumption is
  carried by YouTube's natural ordering, not by an explicit "original
  language" attribute (the library doesn't expose one).
- Returns the chosen `Transcript`; the caller then `transcript.fetch()`s
  it.
- Raises `NoTranscriptFound` (library-native) if neither category
  yielded a match.

Mapping `FetchedTranscript` → `TranscriptResult`:

- `text` = `" ".join(snippet.text for snippet in fetched)` (or
  `"\n".join(...)` — implementer's call, body rendering re-segments
  anyway).
- `segments = [Segment(start_ms=int(s.start * 1000),
                       end_ms=int((s.start + s.duration) * 1000),
                       text=s.text,
                       speaker=None) for s in fetched]`.
  - If the Snippet object doesn't expose `duration` as an attribute,
    fall back to `fetched.to_raw_data()` and read each dict's
    `"duration"` key (the field is in the raw-data shape and pinned
    in the verbatim docs).
- `language = fetched.language_code` (the ISO code, not the
  human-readable `fetched.language`).
- `duration_seconds = max((s.start + s.duration) for s in fetched)`
  — the end of the last caption segment.
- `model = None`.
- `provider = "youtube-captions"`.
- `job_id = None`.

`PreparedTranscript` construction:

```text
PreparedTranscript(
    kind="youtube_captions",
    original_uri=f"https://youtu.be/{video_id}",
    transcript=<built TranscriptResult>,
    title=<--title override, or oembed title, or None>,
    workspace=workspace,
    extra={
        "video_id": video_id,
        "caption_type": "manual" if not chosen.is_generated else "auto",
    },
)
```

## 4. oembed title resolution

In `sources/youtube.py`, helper `_fetch_oembed_title(video_id)`:

- GET against
  `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=<ID>&format=json`
  (URL-encoded). 10-second timeout.
- Parse JSON, return `data["title"]` if present, else `None`.
- **Fail-soft on every error path**:
  - Non-200 (401/403/404 from age-restricted / region-locked / deleted)
    → `None`.
  - `requests.RequestException` → `None`.
  - `json.JSONDecodeError` → `None`.
  - Missing `"title"` key → `None`.
- Validate the returned title using the same `validate_title` helper
  Drive uses (`transcriber.core.title.validate_title`). A title with
  `/`, `\`, `..`, leading `.`, `\0`, or control characters falls
  through to `None` — the user hasn't typed this title, so a malicious
  one from a public video would be a real attack vector.
- Log at `DEBUG` for any failure (oembed failure is a normal outcome
  on a non-trivial fraction of videos, not WARN-worthy).

The CLI's existing title-resolution order — `--title` flag wins → then
source's resolved title (here: oembed result) → then a final fallback
— matches the Drive pattern in `cli.py` lines 386-416. No new branch
needed if `YouTubeSource.prepare` already returns a `PreparedTranscript`
with `title` populated (or None).

## 5. tenacity retry

Apply `tenacity.retry` to the `_pick_transcript` + `fetch()` calls
(implementer's call whether to wrap each separately or wrap the
captions-fetch pipeline as one unit):

- Reuse the existing `_with_retry`-style decorator pattern from
  `providers/assemblyai.py`. Move it to a shared location
  (`core/retry.py` or similar) if the duplication bothers; otherwise
  inline-define in `sources/youtube.py`.
- 3 attempts, exponential backoff (1s/2s/4s).
- Retry on `requests.ConnectionError`, `requests.Timeout`, plus any
  other network-layer exception type the library re-raises from its
  internal HTTP path (verify at impl time — the library may wrap
  network errors in `CouldNotRetrieveTranscript` internally; if so,
  there's nothing to retry at our layer and the wrapper is a no-op).
- **Never retry** on any `CouldNotRetrieveTranscript` subclass — they
  are all deterministic in a single run:
  - `TranscriptsDisabled` / `NoTranscriptFound` / `VideoUnavailable` /
    `VideoUnplayable` / `InvalidVideoId` / `AgeRestricted` won't
    change with a retry.
  - `IpBlocked` / `RequestBlocked` won't unblock in 4 seconds.
- After-retries failures raise the library's exception cleanly; the
  CLI catches in §7.

## 6. Source dispatch

Update `src/transcriber/sources/__init__.py`:

- Add a YouTube arm to `resolve_source(uri)`:
  - Hostname match against
    `{"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}`
    (Phase 2 / F2's hostname-match rule, lifted from `docs/PLAN.md`).
  - Returns `YouTubeSource` if matched.
- The existing reject-not-swallow catch-all (any unrecognised `://`
  URI raises `SourceInputError`) keeps its behaviour. The
  "URI scheme not supported" message updates to mention YouTube as
  a third accepted form (alongside file paths and `drive://`).
- Future Slice 2 (yt-dlp audio fallback) will share the same
  hostname-match arm — but its routing decision ("captions first,
  audio fallback if disabled") lives one level higher (in the
  source itself, or in the CLI). Not this slice's concern.

## 7. CLI wiring — branch on `PreparedTranscript`

Update `src/transcriber/cli.py`:

- After `media = source_cls.prepare(...)`, branch on:
  - `isinstance(media, PreparedTranscript)` → captions path:
    - Skip the budget gate entirely (no provider, no spend).
    - Skip `extract_audio`.
    - The `TranscriptResult` is already in `media.transcript`.
    - INFO log: video ID, language code, caption type, whether oembed
      title resolved.
    - Pass `media` through to formatter + output write.
  - Else (`PreparedMedia`): existing flow unchanged — `media.remote_url`
    branch for Drive, else local upload path.
- `--language` flag check: if `isinstance(media, PreparedTranscript) and language is not None`, log INFO
  ("captions source: --language ignored, returned track is
  <language_code>") and ignore. **Do not error.** The flag is
  meaningful on AssemblyAI / future Phase 5 providers — silently
  ignoring it on captions sources keeps the CLI ergonomic when the
  user has the flag set in a shell alias or env-driven defaults.
- Output filename derivation extends the existing chain (cli.py
  lines 386-416):
  - `--title` provided → `title_to_stem(--title)`
  - Else `media.title` populated (oembed result from `YouTubeSource`) →
    `title_to_stem(media.title)`
  - Else (oembed failed) → fall back to `media.extra["video_id"]`
- Existing `atomic.resolve_collision(output)` handles filename
  collision suffix unchanged.

Update the no-captions error wording per the validation file:

```
[red]error:[/red] Video has no usable captions:
  https://youtu.be/<VIDEO_ID>

Either the creator disabled captions or no auto-generated track is
available. Audio-download fallback (yt-dlp + local ASR) is planned
for Phase 2 Slice 2 — tracked at:
  https://github.com/manjunath84/SSM-Transcriber/issues/21

Workaround today (uses Phase 1 local ASR, $0):

  uv run yt-dlp -x --audio-format wav -o /tmp/<VIDEO_ID>.wav "<URL>"
  uv run ssm-transcriber transcribe /tmp/<VIDEO_ID>.wav
```

`<VIDEO_ID>` and `<URL>` are substituted from the actual user input.

## 8. Markdown formatter — read `provider`/`model`/`job_id` from result

Update `src/transcriber/formatters/markdown.py`:

- Replace the hardcoded `("provider", _yaml_string("assemblyai"))` with
  `("provider", _yaml_string(result.provider))`.
- Replace the hardcoded
  `("assemblyai_job_id", _yaml_string(result.job_id))` with
  `("assemblyai_job_id", _yaml_string(result.job_id) if result.job_id else "null")`.
  Field name stays `assemblyai_job_id` for downstream-parser
  stability (per §"Constraints" in requirements.md).
- `("model", ...)` becomes
  `_yaml_string(result.model) if result.model else "null"`.
- **New `caption_type` insertion:** when
  `media.kind == "youtube_captions"`, insert
  `("caption_type", _yaml_string(media.extra["caption_type"]))`
  between the `model` and `diarized` entries.
- `_source_uri(media)` gains a `youtube_captions` branch: return
  `media.original_uri` (which is already the canonical
  `https://youtu.be/<ID>`).
- `render()`'s `media.local_path is not None` check stays — needs to
  also handle the `PreparedTranscript` case where `local_path` doesn't
  exist as a field at all. Implementer's call whether to type
  the formatter parameter as `PreparedSource` (Protocol) and use
  `isinstance` for the branches, or keep two render signatures.
  The Protocol approach is the cleaner refactor.
- Summary blockquote in `_body()`: for captions sources, swap
  `assemblyai/<model>` for `youtube-captions (<caption_type>)`. The
  `<caption_type>` comes from `media.extra["caption_type"]`.
- For captions, the segment renderer skips speaker prefixes
  (`include_speakers=True` is fine; no segment has a speaker set,
  so the existing `if include_speakers and seg.speaker:` check
  naturally produces a no-prefix output).

## 9. Tests

Unit tests with mocked HTTP cover all paths in `validation.md`
§"Test cases":

- New `tests/unit/test_youtube_source.py`:
  - URL parsing cases (all eight accepted forms → same video ID;
    each rejected form → `SourceInputError`).
  - Manual-captions path → `PreparedTranscript` with
    `caption_type="manual"`.
  - Auto-captions path → `PreparedTranscript` with
    `caption_type="auto"`.
  - Track resolver prefers manual over auto.
  - `TranscriptResult` field mapping correctness
    (`segments[*].start_ms`, last-segment-end `duration_seconds`,
    `language_code`, `provider="youtube-captions"`,
    `model=None`, `job_id=None`).
  - Each documented exception → correct exit code mapping (via the
    CLI test below) AND correct error-message text (here).
  - Tenacity retry: a `requests.ConnectionError` on first call →
    second call succeeds. Three consecutive transient errors →
    library exception raised cleanly.
  - oembed: 200 with JSON body → title extracted. 401, 403, 404,
    timeout, missing-`title`-key, JSON-decode-error, hostile title
    (`../foo`, `a/b`) → fall through to `None`.
  - **Mocking strategy:** `monkeypatch.setattr(YouTubeTranscriptApi,
    "list", stub)` and `monkeypatch.setattr` on the Transcript
    object's `fetch` method. NOT `responses` — the body-matcher
    rule doesn't apply because our code doesn't construct the
    outbound request body. The oembed mock uses `responses` with
    URL+query-params match (we DO construct the query string).
- New `tests/unit/test_source_dispatch.py` extension (or new file
  if needed): all four YouTube hostnames route to `YouTubeSource`.
- Extend `tests/unit/test_provider_types.py`: `TranscriptResult`
  with `provider`, `model=None`, `job_id=None` constructs cleanly.
  Existing AssemblyAI shape still validates.
- Extend `tests/unit/test_markdown_formatter.py`:
  - Render against a `PreparedTranscript` (no `local_path` at all)
    → frontmatter `source_kind: youtube_captions`,
    `provider: youtube-captions`, `model: null`,
    `caption_type: manual` or `auto`, `assemblyai_job_id: null`,
    `diarized: false`, `speakers: null`.
  - Body summary contains `youtube-captions (manual)` or
    `youtube-captions (auto)`, NOT `assemblyai/<model>`.
  - Existing Slice 1 / Drive Slice 2 render cases still pass.
- Extend `tests/unit/test_cli.py`:
  - Captions happy path: mocked `YouTubeSource.prepare` returning a
    `PreparedTranscript` → output written; budget gate NOT called.
  - Captions + `--budget free` → exits 0 (no router invocation).
  - Captions + `--language en` on an `es`-track video → INFO log
    asserts "ignored"; output uses `es` track.
  - Each error category from §7 maps to the documented exit code.
  - `--title "Session 17"` on a captions source → output uses
    `Session-17-<date>.md`, frontmatter `title: "Session 17"`.
  - No `--title`, oembed returns title → output uses oembed title.
  - No `--title`, oembed fails → output uses video ID stem.

Manual: extend `tests/manual/end_to_end.md` with a YouTube captions
scenario — single real run against one public video the user knows
has captions, plus one that doesn't (verifies the error-message
wording in the real CLI output). Do NOT add real YouTube fixtures to
CI; the mocked unit tests cover all branches.

## 10. Per-PR teaching artifacts

Once implementation lands and before opening the impl PR:

- Draft `docs/learn/prs/pr-NNN-youtube-captions-source-impl.md` using
  the repo's explainer template. Focus on implementation-phase
  learnings, not the spec-phase decisions already captured in the
  spec PR's explainer. Worth highlighting:
  - How the `PreparedSource` Protocol refactor actually played out in
    practice — was the cleaner separation worth the larger blast
    radius, or did `PreparedMedia | PreparedTranscript` unions show
    up in places we didn't predict?
  - Whether `youtube-transcript-api`'s post-1.0 API matched the ctx7
    docs verbatim, or whether real-call behaviour diverged in any
    way the spec missed.
  - oembed fail-soft path — how often did it actually fall through
    during the manual runbook vs producing a title? Real-world
    fail-rate informs whether to invest in a better fallback later.
  - Whether the no-captions error message landed for the user when
    they actually hit it (single real run on a captionless video).
- Append the PR entry at the top of `docs/learn/journey.md`.
- Append the PR row to `docs/learn/prs/README.md` index.
- Interview-prep STAR hook in `docs/learn/interview-prep.md`: the
  "captions-first instead of audio-download" architectural choice
  ships a real cost-shape decision worth capturing. Frame as: free
  caption path covers the common case at $0; audio fallback is a
  separate Phase 2 Slice 2 with a different code surface; the
  `PreparedSource` Protocol generalizes the F2 contract to support
  "transcript-already-prepared" sources without dishonest naming.
- No new glossary or python-notes entries expected unless something
  surprising surfaces during impl (e.g., a Python typing pattern
  specific to `Protocol` + `dataclass`).
- Update `specs/roadmap.md`: Phase 2 Slice 1 status from `pending` to
  `done — YouTube captions passthrough shipped`.
- Update `docs/PLAN.md` §"Phase 2 — Add YouTube Support" to reflect
  Slice 1 shipped; Slice 2 (yt-dlp audio fallback) remains open.

## 11. Exit gate

Implementation is complete only when **every** item in
`validation.md` §"Success criteria" has produced concrete evidence
(test output, command results, manual-runbook log) shown to the
user, AND the user has explicitly approved the impl PR for merge. No
silent claims of "tests pass" without showing the run.
