# Validation — YouTube Source (Captions Passthrough)

> **Reading note for spec-PR reviewers.** This file describes the
> bar the *implementation PR* must clear, not this spec PR. The
> spec PR's done bar is: "the seven brainstorm decisions are
> recorded; the three files are internally consistent; the verbatim
> `youtube-transcript-api` API surface + oembed response are pinned
> in `requirements.md` §"Reference calls (verbatim)" with the
> 2026-05-12 retrieval date." The criteria below come into play
> when the implementation PR opens — the implementer references
> this file while building and the reviewer references it before
> merge.

## Success criteria

Each item below requires **concrete evidence** (command output, file
contents, or manual-runbook log) before this slice can be declared
done. "Tests pass" is not evidence; the test run is.

1. `uv run pytest` passes including all new tests in §Test cases below.
   Evidence: test runner output with the count of new tests.
2. `uv run ruff check src/ tests/` clean.
3. `uv run mypy src/ tests/` clean. The new `PreparedSource` Protocol
   must type-check in the formatter signature and the source dispatch
   return type.
4. The manual integration runbook
   (`tests/manual/end_to_end.md` — YouTube scenario) has been
   executed once against a real public video the user knows has
   captions, and produces a markdown file matching the documented
   frontmatter schema. Evidence: the resulting `.md` file
   (frontmatter visible) and the captured CLI stdout (showing INFO
   logs for video ID, language, caption type, oembed result).
5. The manual runbook has also been executed once against a real
   public video the user knows does NOT have captions (e.g., a
   silent video or one where the creator disabled them) — verifies
   the no-captions error wording lands correctly in real CLI
   output. Evidence: CLI stdout showing the exact error message
   from `plan.md` §7 with substituted `<VIDEO_ID>` and `<URL>`.
6. `uv run ssm-transcriber transcribe "https://youtu.be/<NO_CAPTION_ID>"`
   exits `2` with the documented "no usable captions" message
   pointing at issue #21. Evidence: command + exit code shown.
7. `uv run ssm-transcriber transcribe "https://www.youtube.com/playlist?list=PL..."`
   exits `2` with "supply a single video URL". Evidence: command +
   exit code shown.
8. `uv run ssm-transcriber transcribe "https://youtu.be/<CAPTIONED_ID>" --budget free`
   succeeds (exits `0`). Captions path bypasses the budget router.
   Evidence: command + exit code shown.
9. `git diff main` scope is limited to:
   - `src/transcriber/sources/{base,youtube,__init__}.py`
   - `src/transcriber/providers/base.py`,
     `src/transcriber/providers/assemblyai.py`
     (TranscriptResult field migration only)
   - `src/transcriber/formatters/markdown.py`
   - `src/transcriber/cli.py`
   - `pyproject.toml` (one new dep), `uv.lock` (regenerated)
   - `tests/unit/` (new + extended files per §Test cases)
   - `tests/manual/end_to_end.md` (YouTube scenario added)
   - `docs/learn/` (per-PR teaching artifacts)
   - `specs/2026-05-12-youtube-captions-source/` (this folder)
   - `specs/roadmap.md` (one status-line update on Phase 2)
   - `docs/PLAN.md` §Phase 2 (status flip on Slice 1)

   No changes to `.env.example`. Evidence: `git diff main --stat`.

## Test cases

Each case verifies an externally observable behavior, not an
internal implementation detail.

### URL parsing

Each of the following accepted forms must extract to the same 11-char
video ID `dQw4w9WgXcQ`:

1. `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
2. `https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42`
3. `https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234&index=2`
   (the `list` parameter is ignored — it's a playlist context, not
   a routing signal)
4. `https://youtube.com/watch?v=dQw4w9WgXcQ`
5. `https://m.youtube.com/watch?v=dQw4w9WgXcQ`
6. `https://youtu.be/dQw4w9WgXcQ`
7. `https://youtu.be/dQw4w9WgXcQ?t=42`
8. `https://www.youtube.com/embed/dQw4w9WgXcQ`
9. `https://www.youtube.com/shorts/dQw4w9WgXcQ`
10. `https://www.youtube.com/live/dQw4w9WgXcQ`

Each of the following rejected forms must raise `SourceInputError`
(parametrised test):

11. `https://www.youtube.com/playlist?list=PL...` → "supply a single
    video URL" message.
12. `https://www.youtube.com/channel/UC1234567890abcdefghijkl`
13. `https://www.youtube.com/@channel-name`
14. `https://www.youtube.com/` (homepage)
15. `https://www.youtube.com/watch?v=tooshort` (ID fails 11-char regex)
16. `https://www.youtube.com/watch` (no `v=` param)
17. `https://www.youtube.com/watch?v=valid+chars+but+13` (extracted
    ID fails regex)
18. `https://www.youtube.com/embed/` (no ID after segment)

### Source dispatch

19. `resolve_source("https://youtu.be/dQw4w9WgXcQ")` → `YouTubeSource`
20. `resolve_source("https://www.youtube.com/watch?v=...")` →
    `YouTubeSource`
21. `resolve_source("https://m.youtube.com/watch?v=...")` →
    `YouTubeSource`
22. `resolve_source("https://www.youtube.com/shorts/...")` →
    `YouTubeSource`
23. `resolve_source("drive://...")` → `DriveSource` (regression)
24. `resolve_source("./video.mp4")` → `LocalSource` (regression)
25. `resolve_source("https://vimeo.com/123")` →
    `SourceInputError` with the "URI scheme not supported"
    message (mentions file paths, `drive://`, and YouTube URLs).

### `PreparedTranscript` construction

26. `PreparedTranscript(kind="youtube_captions", ...)` with all
    fields set → constructs cleanly. Round-tripping a manually-built
    instance through `dataclasses.asdict` preserves shape.
27. `PreparedSource` Protocol structural conformance: both
    `PreparedMedia` and `PreparedTranscript` instances expose the
    five shared attributes (`kind`, `original_uri`, `title`,
    `workspace`, `extra`) — asserted via `hasattr` rather than
    `isinstance(x, PreparedSource)`, since the latter requires
    `@runtime_checkable` and the Protocol's primary purpose is
    static `mypy` typing (criterion #3), not runtime dispatch.

### `YouTubeSource.prepare` — mocked library

Each case uses
`monkeypatch.setattr(YouTubeTranscriptApi, "list", stub)`:

28. **Manual track present.** `list()` returns a `TranscriptList`-like
    object whose iteration yields one manual + one auto track.
    Resolver picks the manual track. `PreparedTranscript.extra
    ["caption_type"] == "manual"`.
29. **Only auto present.** `list()` yields a single auto track.
    Resolver picks it. `extra["caption_type"] == "auto"`.
30. **Empty list / no tracks.** Resolver raises `NoTranscriptFound`
    (library-native).
31. **`TranscriptsDisabled` from `list()`.** Propagates cleanly to
    the CLI layer.
32. **Snippet → `Segment` mapping.** A fetched track with snippets
    `[(start=0.0, duration=1.5, text="hello"),
      (start=1.5, duration=2.0, text="world")]` produces segments
    `[(start_ms=0, end_ms=1500, text="hello"),
      (start_ms=1500, end_ms=3500, text="world")]`. Speaker is
    `None` on every segment.
33. **`duration_seconds` derivation.** Same snippet input as #32 →
    `result.duration_seconds == 3.5`.
34. **`TranscriptResult` field values.** `result.provider ==
    "youtube-captions"`, `result.model is None`, `result.job_id is
    None`, `result.language == "en"` (or whatever
    `language_code` the mocked track exposed).

### Tenacity retry

35. First call raises `requests.ConnectionError`; second call
    succeeds → fetch returns successfully after one retry. Backoff
    asserted via `time.sleep` mock or tenacity's `before_sleep`
    hook.
36. Three consecutive `requests.Timeout` → retry exhausts and the
    final exception propagates (or wraps cleanly into a
    `ProviderError`-equivalent for the captions path; implementer's
    call).
37. `IpBlocked` raised by the library → **not retried**. The
    exception propagates immediately. (Counter-test against
    accidentally widening the retry whitelist.)
38. `TranscriptsDisabled` raised by the library → **not retried.**
    (Same.)

### oembed title resolution (mocked HTTP via `responses`)

39. Mocked GET to the oembed URL returns the verbatim Rick Astley
    response from `requirements.md` §"Reference calls (verbatim)"
    → title extracted as
    `"Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)"`.
    The mock asserts the URL + query parameters
    (`url=https%3A//www.youtube.com/watch%3Fv%3D<ID>&format=json`)
    via `responses.matchers.query_param_matcher` (or equivalent).
40. Mocked 401 → `None`. No exception escapes the helper.
41. Mocked 403 → `None`.
42. Mocked 404 → `None`.
43. Mocked timeout (`requests.Timeout`) → `None`.
44. Mocked 200 with missing `"title"` key → `None`.
45. Mocked 200 with malformed JSON → `None`.
46. Mocked 200 with a hostile title (`../foo`, `a/b`,
    `path\\traversal`, leading `.`) → `None` (rejected by
    `validate_title`).

### CLI — captions happy paths

47. `transcribe "https://youtu.be/<CAPTIONED_ID>"` with
    `YouTubeSource.prepare` mocked → output written to
    `{output_dir}/{oembed-title-stem}-{date}.md`; frontmatter
    `title` is the oembed title; `source_uri:
    https://youtu.be/<CAPTIONED_ID>`; `source_kind:
    youtube_captions`; `caption_type: manual`; `assemblyai_job_id:
    null`; `model: null`. Budget router NOT called (assert via
    mock).
48. Same command with `--title "Custom Title"` → output filename
    contains `Custom-Title`; frontmatter `title: "Custom Title"`.
    **oembed is NOT fetched** when `--title` is provided — the
    user has supplied the canonical title, so the network round
    trip would be pure waste. The
    `test_prepare_skips_oembed_when_explicit_title_provided` test
    locks this; the earlier draft of the spec (asserting "fetched
    for telemetry") was reconciled to match the implementation
    during PR #31's test-analyzer review.
49. Same command, oembed mock returns 404 → output filename uses
    the video ID stem (e.g., `dQw4w9WgXcQ-{date}.md`); frontmatter
    `title` is the video ID.
50. Same command with `--budget free` → exits 0; budget router NOT
    called.
51. Same command with `--language en` on a track whose
    `language_code` is `es` → output uses `es` track; INFO log
    contains "ignored, returned track is es".
52. Same command with `--budget low` → also exits 0 (the captions
    path is uniform across budget tiers; no gate fires).

### CLI — captions error paths

Each case exits with the documented code AND a stdout/stderr
message containing the documented key phrases:

53. `TranscriptsDisabled` → exit `2`, message contains "no usable
    captions" and links to issue #21.
54. `NoTranscriptFound` (after resolver iterates and finds nothing)
    → exit `2`, same message text as #53.
55. `VideoUnavailable` → exit `2`, message contains
    "Video unavailable" or library-native `.reason` text.
56. `VideoUnplayable` → exit `2`, message includes the library's
    `.reason` field.
57. `InvalidVideoId` → exit `2`. (Note: distinguish from our own
    URL-parsing exit `2`. Library-side rejection is observable
    only with a regex-valid ID that YouTube doesn't recognise — a
    rare path; the test mocks the library raising this directly.)
58. `AgeRestricted` → exit `2`, message explains auth-only path
    and that Slice 2 won't help.
59. `IpBlocked` → exit `3`, message names the pinned library
    version and suggests trying later.
60. `RequestBlocked` → exit `3`, same as #59.
61. `CouldNotRetrieveTranscript` (catch-all) → exit `3`.
62. Three retries on `requests.ConnectionError` exhaust → exit `3`.

### Markdown formatter — captions output

63. Render against a `PreparedTranscript(kind="youtube_captions",
    extra={"caption_type": "manual", "video_id": "dQw4w9WgXcQ"},
    title="Test Title", ...)` with a `TranscriptResult(provider=
    "youtube-captions", model=None, job_id=None, ...)` →
    frontmatter contains:
    ```yaml
    title: Test Title
    source_uri: https://youtu.be/dQw4w9WgXcQ
    source_kind: youtube_captions
    duration_seconds: <value>
    language: en
    provider: youtube-captions
    model: null
    caption_type: manual
    diarized: false
    speakers: null
    assemblyai_job_id: null
    created: <date>
    ```
    Order matters — assertion is on substring + ordering.
64. Body summary contains `youtube-captions (manual)` (NOT
    `assemblyai/<anything>`).
65. Body transcript section: each segment rendered with
    `[mm:ss]` timestamp; no `**Speaker X:**` prefixes (all
    segments have `speaker=None`).
66. Render against an auto-track `PreparedTranscript` →
    frontmatter `caption_type: auto`; body summary
    `youtube-captions (auto)`.
67. Render against an AssemblyAI `PreparedMedia` (regression) →
    `provider: assemblyai`, `model: universal-3-pro`,
    `assemblyai_job_id: <real>`; NO `caption_type` field present;
    body summary `assemblyai/universal-3-pro`.
68. Render against a Drive `PreparedMedia` (regression) →
    `provider: assemblyai`, `source_kind: google_drive`,
    `assemblyai_job_id: <real>`; NO `caption_type` field.

### Regression — existing Slice 1 / Drive Slice 2 behaviour

69. All existing `tests/unit/test_assemblyai_provider.py` cases
    pass with the new `TranscriptResult.provider` /
    `Optional[model]` / `Optional[job_id]` fields.
70. All existing `tests/unit/test_markdown_formatter.py` Slice 1
    and Drive cases still pass.
71. All existing `tests/unit/test_cli.py` local + Drive tests
    still pass.
72. All existing `tests/unit/test_google_drive.py` cases pass
    unchanged.

## Edge cases / what could break

These are not always full test cases, but they ARE behavior the
implementation must handle gracefully. Some become tests in
§"Test cases" above; the rest are documented behavior verified
once during the manual runbook or by inspection.

1. **Video has captions enabled but `list()` returns empty
   collection.** Unusual but possible YouTube-side state. Resolver
   raises `NoTranscriptFound`; CLI exits 2 with the standard
   no-captions message.
2. **Video has ONLY auto-translated tracks** (e.g., a Hindi video
   with no original Hindi track but auto-translated English). Per
   spec we exclude translated tracks; resolver sees no manual or
   auto-generated original-language track and raises
   `NoTranscriptFound`. The user gets the standard no-captions
   message + Slice 2 pointer.
3. **Snippet attribute access.** Resolved at impl time 2026-05-13:
   `FetchedTranscriptSnippet`'s constructor signature is
   `(text: str, start: float, duration: float)` — all three are
   real instance attributes. The implementation accesses them
   directly; no `to_raw_data()` fallback is required. If a future
   library release changes the snippet class shape, the
   `test_segment_mapping_uses_milliseconds_and_last_segment_duration`
   test catches the regression.
4. **Video has captions but oembed returns 404** (private video
   that YouTube still serves captions for somehow, or a deletion
   race). Captions render with the video ID stem as title;
   no failure surfaced to the user.
5. **oembed response contains a `title` with shell-unsafe
   characters** (creator-controlled metadata — any third-party
   uploader can name a video `foo / bar`). `validate_title` rejects
   the title; falls through to video ID stem. Same defence as Drive's
   `_fetch_drive_filename` pattern.
6. **YouTube changes the oembed endpoint shape.** Endpoint is
   considered stable by YouTube; if it breaks, fail-soft (return
   None) means the user gets video-ID-stem filenames. They'd file
   an issue and we'd ship a fix.
7. **`youtube-transcript-api` library is upgraded mid-pin range.**
   Pin is `>=1.0,<2.0` (or whichever range is stable at impl
   time). Within the range, breaking changes shouldn't occur;
   between ranges, the PR that bumps the pin verifies against the
   §"Reference calls (verbatim)" section.
8. **YouTube changes its frontend and the library breaks.**
   Surfaces as `CouldNotRetrieveTranscript` (or one of its
   subclasses we don't have a specific handler for). CLI exit 3
   with a message naming the pinned library version and
   suggesting the user check for a library update.
9. **Network drops mid-fetch.** Tenacity retries on
   `requests.ConnectionError` / `Timeout` 3 times. If all retries
   exhaust, exit 3.
10. **User Ctrl-C during captions fetch.** `RunWorkspace` cleanup
    runs; no artifacts written. No behaviour difference from Slice 1.
11. **Cache hit semantics.** N/A — captions path doesn't use F3
    cache (deferred per requirements). Re-running `transcribe` on
    the same URL re-fetches from YouTube.
12. **Frontmatter schema change visible to downstream consumers.**
    The new `caption_type` field is additive (omitted for
    non-captions sources). Existing parsers (NotebookLM, Obsidian,
    knowledge-base distill workflow) see no breaking change.

## Definition of done

This slice is **done** when, in this order:

1. All §"Success criteria" items 1–9 have produced concrete evidence
   shown to the user.
2. All §"Test cases" pass in the test run.
3. The PR explainer, journey entry, prs/README index row,
   interview-prep STAR hook have been written and committed.
4. `specs/roadmap.md` Phase 2 status has been updated to reflect
   Slice 1 as shipped.
5. `docs/PLAN.md` §"Phase 2 — Add YouTube Support" reflects Slice 1
   as shipped; Slice 2 (yt-dlp audio fallback) remains pending.
6. The user has explicitly approved the impl PR for merge.

None of the above are optional.
