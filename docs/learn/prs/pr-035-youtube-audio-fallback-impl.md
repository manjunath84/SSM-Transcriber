# PR #35 — Implementation: YouTube Source (yt-dlp Audio Fallback)

**Merged:** 2026-05-13 (squash `077b26a`)  |  **Branch:** `feat/youtube-audio-fallback-impl` (deleted)  |  **Reviews:** Codex (4 findings, all P1+P2 fixed pre-merge), pr-review-toolkit five-agent pass (2 critical + 8 important, all fixed pre-merge)
**Spec PR:** [#34](https://github.com/manjunath84/SSM-Transcriber/pull/34) ([explainer](pr-034-youtube-audio-fallback-spec.md))
**Journey entry:** [`../journey.md#pr-35--implementation-youtube-source-yt-dlp-audio-fallback`](../journey.md#pr-35--implementation-youtube-source-yt-dlp-audio-fallback)

## The problem in one paragraph

PR #34 committed the spec for Phase 2 Slice 2 (issue #21): when
captions are missing, download audio with `yt-dlp` and route it
through the existing local-file pipeline → AssemblyAI. This PR is
the implementation. After it merges, every viewable YouTube URL —
captioned or not — produces a usable transcript. Captioned videos
stay `$0`; captionless videos cost real money but only after explicit
user consent at the budget gate.

## What changed, by phase

Three implementation commits landed the slice in plan-task-group
order on the feature branch, plus a Phase D docs commit and two
post-review fix commits. main collapsed all six into the single
squash commit `077b26a`; the phase-SHAs below reference the feature
branch's pre-merge history (now deleted) for teaching continuity.

### Phase A — source layer (commit `8f6e36f`)

Adds the new types and source methods. No CLI wiring yet — Slice 1's
existing tests still pass byte-for-byte because the CLI's stubbed
prepare() in `test_captions_library_exception_matrix` bypasses the
new wrap (the test substitutes prepare() entirely rather than
exercising the captions-library exception path that triggers the
wrap).

- `SourceKind` literal: adds `youtube_audio`, removes the dead
  `youtube` literal Slice 1 left behind.
- New types in `sources/youtube.py`:
  - `AudioProbe` frozen dataclass (`duration: int`, `title: str`)
  - `NoCaptionsAvailable` exception — wraps `TranscriptsDisabled` /
    `NoTranscriptFound` so the CLI can route them through the
    budget-aware audio-fallback handler. Original exception preserved
    in `__cause__`.
  - `ProbeDurationUnknown` exception — raised when probe's `duration`
    is `None` or `<=0` (live streams, premieres). Saves the user from
    a fake `$0.00` cost prompt.
- `_YDL_OPTS_BASE` module constant — 7 keys (`quiet`, `no_warnings`,
  `format: "bestaudio/best"`, `retries=3`, `fragment_retries=3`,
  `socket_timeout=30`, `noplaylist=True`). Matches the spec's
  `## Reference calls (verbatim)` byte-for-byte and is pinned by
  `test_ydl_opts_base_matches_spec_verbatim`.
- `_probe_metadata` and `_download_audio` helpers. yt-dlp imported
  locally (the module is ~50 MB after extraction-registry init;
  captions-only happy path stays lightweight).
- `YouTubeSource.probe_audio()` and `download_audio()` — thin
  staticmethods over the helpers. `download_audio` builds
  `PreparedMedia(kind="youtube_audio", duration_seconds=float(probe.duration),
  extra={..., "probe_duration": str(probe.duration)})` — the field
  ordering and types match `sources/base.py:PreparedMedia` (the
  spec's pre-Codex draft got this wrong; the fix landed in PR #34
  before code was written).

A side-finding caught mid-Phase: `workspace.path` is a method
(`path(name) -> Path`), not an attribute. The spec implied
attribute-style access; a `TypeError` from a download-audio test
surfaced the mismatch. Corrected in both production code and tests.

26 new tests in `test_youtube_source.py` (52 → 78). TDD discipline
throughout — each test written before code, each saw a real failure
for the right reason (ImportError, AttributeError, TypeError, or
AssertionError on the missing behaviour) before turning green.

### Phase B — CLI wiring (commit `bd0f8b3`)

Four sub-phases collapsed to one commit because they're tightly
coupled (the budget-aware message has no meaning without the low+
path actually working).

- `_no_captions_message(source_uri, budget)` becomes budget-aware.
  On `free` budget, the message points the user at `--budget low`.
  On paid budgets, the function raises defensively — the caller-side
  contract is "only call this on free", and the audio-fallback path
  fires silently otherwise.
- The transcribe command grows a new `except NoCaptionsAvailable`
  handler before the `YouTubeTranscriptApiException` catch:
  - Free budget → emit budget-aware message → exit 2. No probe
    attempted (the spec's pre-flight short-circuit).
  - Paid budget → `probe_audio` → `budget_check` (with the spec's
    verbatim cost summary string) → `download_audio` → fall through
    to the existing PreparedMedia local-path pipeline.
- New `_handle_yt_dlp_exception(exc, source_uri) -> (exit_code, message)`
  helper implementing the spec §4c matrix. A parametrized test
  covers all 10 rows. Two adjacent fixes during impl:
  - **Sibling-not-subclass discovery.** A test failure for
    `UnavailableVideoError` surfaced that it doesn't inherit
    `ExtractorError` — both inherit `YoutubeDLError` directly.
    Same for `PostProcessingError` (sibling of `DownloadError`).
    A narrow `(ExtractorError, DownloadError)` except tuple would
    silently miss those exception types. Switched both try/except
    clauses to catch `YoutubeDLError + OSError`. This is exactly
    the regression a 10-row parametrized matrix catches that a
    single happy-path test wouldn't.
  - **Case-sensitive substring assertions are brittle.** The
    matrix test asserted lowercase substrings ("audio extraction
    failed") against production messages with Title Case ("Audio
    extraction failed"). Updated the test to `.lower()` both
    sides — the casing is presentation, not contract.
- §4d filename arm: new `kind == "youtube_audio"` branch in the
  filename-derivation cascade. Also changed the preceding
  `media.title is not None` check to a truthy check so an empty
  probe title falls through to the source-kind fallback instead of
  producing a leading-dash filename.
- §4e budget bypass: the existing local-file pipeline's post-extract
  `budget_check` is wrapped in `if media.kind != "youtube_audio":` so
  the audio-fallback path doesn't re-fire the gate. Locked by a
  test that counts prompt invocations.

The CLI's `_handle_youtube_exception` loses its `TranscriptsDisabled` /
`NoTranscriptFound` branch — those are unreachable post-Phase A
since `prepare()` wraps them.

Test surface grows by 13 in `test_cli.py` (82 → 95), 1 outdated
test removed (the old issue-#21-pointer "no captions" test) and
two parametrize rows now routed through `NoCaptionsAvailable`.

The two post-review fix commits added another **+25 tests** on top
(14 from the Codex P1+P2 round, 11 from the pr-review-toolkit
round — probe edge cases, defensive download-response checks,
widened auth markers, AudioProbe invariants, catch-all logger).
Final test count at merge: **371 passing** (was 342 before review).

### Phase C — formatter (commit `c1cdf63`)

The formatter's `_source_uri` already handles `kind="youtube_audio"`
correctly (the if-cascade only special-cases `kind="local"` for
`file://` URIs; everything else falls through to
`return media.original_uri`). No code change in `_source_uri` —
the test pins the behaviour so a future refactor can't accidentally
introduce `file://` for the audio path.

`_resolve_title` needed a new branch. `PreparedMedia` with
`local_path` falls through to `local_path.stem` by default, which
for `youtube_audio` would land on the workspace audio file's stem
(`audio`) — a misleading transcript title for a real YouTube video.
New branch checks `kind == "youtube_audio"` *before* the generic
`local_path.stem` case and returns `extra["video_id"]` (the same
fallback the captions arm uses for empty oembed titles).

5 new formatter tests pin the frontmatter shape, body summary,
empty-title fallback, and field order.

### Phase D — docs (this commit)

`PLAN.md` Slice 2 description rewritten to reflect what actually
shipped (AssemblyAI not faster-whisper). New Slice 2b entry queues
the faster-whisper provider for its own slice. Slice 1's no-captions
message description updated to reflect the new `NoCaptionsAvailable`
routing. `specs/roadmap.md` flipped to complete-with-caveat. Manual
e2e doc gains a Slice 2 section with five steps + recording template.
This explainer + the spec explainer + journey entries land here.

## What this teaches

Three takeaways worth keeping:

**The sibling-not-subclass exception trap.** Catching
`ExtractorError + DownloadError` for a library that uses sibling
exceptions silently misses runtime errors that look exactly like the
ones you're catching. The defence is (a) the common base
(`YoutubeDLError` here, `requests.RequestException` for the captions
side in Slice 1, both via PR #31's silent-failure-hunter finding),
and (b) a parametrized matrix test rather than isolated cases —
the matrix is what surfaces "wait, why didn't that one match?".

**Spec → impl drift is bounded by the impl PR's tests.** The spec
got two reviews before merge (Codex + pr-review-toolkit). All ten
findings landed as spec edits before any code was written. The impl
PR's tests then verified the spec was followed — no spec re-litigation
during code review. The `_YDL_OPTS_BASE` byte-for-byte test is the
load-bearing piece: any drift between the spec's reference call and
the production dict fails CI, not user runs.

**TDD discipline catches API mismatches at the cheapest possible
point.** Three real bugs surfaced mid-impl via test failures, not
runtime errors: `workspace.path` being a method (TypeError on a
download test), `UnavailableVideoError` not inheriting `ExtractorError`
(exit code 1 in the matrix test instead of 2), and Rich line-wrapping
breaking a substring assertion. Each one was a 30-second fix because
the test localised the problem to one assertion. The same mismatches
in a real run would have surfaced as user-facing exit-1 tracebacks
or a confusing "almost worked" outcome.
