# PR #31 — Implementation: YouTube Source (Captions Passthrough)

**Merged:** TBD  |  **Branch:** `feat/youtube-captions-source-impl`  |  **Codex review:** TBD
**Journey entry:** [`../journey.md#pr-31--implementation-youtube-source-captions-passthrough`](../journey.md#pr-31--implementation-youtube-source-captions-passthrough)

## The problem in one paragraph

PR #30 committed the spec triple for Phase 2 Slice 1 (issue #20):
fetch existing YouTube captions via `youtube-transcript-api`, emit a
finished `TranscriptResult` directly, no audio download, no paid
provider call. This PR is the implementation. It's the second feature
loop that uses the `PreparedSource` Protocol + sibling-dataclass
pattern (introduced here for the first time), and the first
captions-only source the project ships.

## What changed (high level, not file-by-file)

Three implementation commits land the slice in plan-task-group order,
plus this teaching-artifacts commit:

1. **Phase A — F2 contract foundation + `TranscriptResult`
   generalization.** Commit `f7300c7`. Adds the new `PreparedSource`
   Protocol and `PreparedTranscript` sibling dataclass in
   `sources/base.py`; extends `SourceKind` with `"youtube_captions"`.
   `TranscriptResult` gains a required `provider: str` field (was
   hardcoded `"assemblyai"` in the formatter) and makes `model` /
   `job_id` Optional (the captions path has no ASR model identifier
   and no remote job ID). AssemblyAI provider sets
   `provider="assemblyai"` on construction. Formatter reads
   `result.provider`, renders `model` / `assemblyai_job_id` as YAML
   `null` when None. The frontmatter field name `assemblyai_job_id`
   stays for downstream-parser schema stability; Phase 5 generalizes
   to `provider_job_id`. 10 existing `TranscriptResult` construction
   sites in tests updated; 2 new tests for the new shape. **202 → 202
   tests, all green.**

2. **Phase B — `YouTubeSource` + oembed + retry.** Commit `5953882`.
   New `src/transcriber/sources/youtube.py`. `_extract_video_id`
   parses the 10 accepted YouTube URL forms (watch with `?v=`, +
   query params, mobile, embed, shorts, live, short-link, mobile)
   into the canonical 11-char `[A-Za-z0-9_-]{11}` ID. Playlist /
   channel / channel-handle / homepage / malformed forms raise
   `SourceInputError` (CLI exit 2). `_pick_transcript` iterates the
   library's `transcript_list`, prefers `not is_generated` (manual)
   over `is_generated` (auto), never calls `.translate()`.
   `_build_transcript_result` maps `FetchedTranscript` snippets to
   the codebase's `TranscriptResult` / `Segment` shape — `start_ms`
   = `int(s.start * 1000)`, `duration_seconds` = end of last segment
   (Q4b: oembed has no `duration` field, verified via real `curl`
   2026-05-12). `_fetch_oembed_title` does one fail-soft GET against
   the public oembed endpoint — non-200, malformed JSON, missing
   key, hostile creator-controlled title (rejected via the same
   `validate_title` helper Drive uses) all return `None`.
   `_fetch_captions` is `@tenacity.retry`-wrapped (3 attempts,
   1s/2s/4s exponential, retries only on `requests.Timeout` /
   `requests.ConnectionError`; never on `CouldNotRetrieveTranscript`
   subclasses). 42 new tests; library pinned to
   `youtube-transcript-api>=1.0,<2.0`.

3. **Phase C — dispatch + CLI branch + formatter caption fields.**
   Commit `5254252`. `resolve_source()` gained a hostname-match arm
   for `youtube.com` / `www.youtube.com` / `m.youtube.com` /
   `youtu.be`. CLI branches on `isinstance(media, PreparedTranscript)`
   *before* `budget_check` fires — captions path skips the budget
   router entirely (`--budget free` is allowed because the path is
   $0). `--language` flag silently ignored on captions sources with
   an INFO log naming the actual returned-track language. New
   `_handle_youtube_exception` helper maps each library exception
   to a documented exit code: `TranscriptsDisabled` /
   `NoTranscriptFound` / `VideoUnavailable` / `VideoUnplayable` /
   `InvalidVideoId` / `AgeRestricted` → exit 2 with user-facing
   messages; `IpBlocked` / `RequestBlocked` / generic
   `CouldNotRetrieveTranscript` / network-layer exhaustion → exit 3.
   No-captions error message points at issue #21 with a copy-paste
   `yt-dlp + uv run ssm-transcriber transcribe` workaround using
   Phase 1's free local-ASR path. Markdown formatter accepts
   `PreparedSource` Protocol; new `_resolve_title` helper
   centralizes the title-fallback chain across all three source
   kinds; inserts `caption_type` field for `youtube_captions`
   sources (omitted for others — additive schema change); body
   summary shows `youtube-captions (manual|auto)` for captions
   instead of `<provider>/<model>`. Side fix: `providers.base`'s
   `PreparedMedia` import moved under `TYPE_CHECKING` to break the
   new cycle `sources.youtube → providers.base → sources.base →
   sources.__init__ → sources.youtube`. `PreparedSource` Protocol
   fields converted to `@property` declarations so frozen dataclasses
   satisfy the Protocol cleanly (otherwise mypy reads them as
   settable). 6 new CLI captions integration tests.

**Final state:** 261 unit tests pass; ruff + mypy clean.

## Why this approach

The seven user-facing decisions and one architectural decision settled
during the brainstorm and spec PR #30 are recorded there; this
explainer focuses on the *implementation-phase* learnings.

The single biggest implementation-phase issue was **the circular import
that surfaced when the formatter test imported `PreparedTranscript`**.
The chain was:

```
sources.youtube imports providers.base (for Segment/TranscriptResult)
  → providers.base imports sources.base (for PreparedMedia type hint)
    → loading sources.base loads the sources package
      → sources/__init__.py imports YouTubeSource from sources.youtube
        → BACK TO sources.youtube, still being loaded
```

The cycle only triggered when the package `__init__.py` eagerly
imported `YouTubeSource`. Three resolution options:

1. **Lazy import inside `youtube.py`** — defer `Segment`,
   `TranscriptResult` imports to function bodies. Localized but
   spreads the workaround across multiple call sites.
2. **Move the YouTubeSource import to lazy inside `resolve_source()`**
   — fixes the cycle but introduces an asymmetry: DriveSource and
   LocalSource stay eager-imported, YouTubeSource is lazy.
3. **Move `providers.base`'s `PreparedMedia` import under
   `TYPE_CHECKING`** — `PreparedMedia` is used only as a type hint
   in `TranscriptionProvider.transcribe()`, so a forward reference
   plus `if TYPE_CHECKING:` works perfectly. Single line change.
   No runtime cost.

Option 3 was the right call. It also captures an architectural
truth: `providers.base` *shouldn't* need a runtime import of
`sources.base` — providers consume `PreparedMedia` instances passed
in by the CLI, never construct them. The `TYPE_CHECKING` guard
makes that explicit. Lesson worth carrying forward: when a circular
import shows up, check whether one side's import is type-only first.

The second implementation-phase issue was **mypy rejecting frozen
dataclasses against a Protocol with bare attribute annotations**.
`class PreparedSource(Protocol): kind: SourceKind` declares `kind`
as a *settable* attribute, but `@dataclass(frozen=True)` makes
`kind` read-only. mypy reports the conflict at every call site that
takes `PreparedSource`. The fix is `@property` declarations on the
Protocol, which signal read-only-compatible. This is the standard
Protocol-vs-frozen-dataclass pattern; worth knowing for next time.

The third implementation-phase issue was **a one-test corruption from
naïve substring replacement**. Trying to bulk-update 10 test fixtures
in `test_cli.py` with `replace_all=true` on `model="universal-3-pro",`
(8-space indent) actually matched 16-space-indented lines too — the
8-space pattern is a substring of the 16-space pattern. Got 16
insertions instead of 10, broke parsing with `provider= provider=`
duplicates. The fix was `git checkout` followed by a `python3 -c
"... re.sub(...) ..."` one-liner that matched whole lines with
`^\s+model=...$` and preserved indent groups. Lesson: when an
auto-tool says "all occurrences replaced," verify the count matches
intent *before* moving on.

## What a reviewer should notice

- **The CLI branches on `isinstance(media, PreparedTranscript)`
  *before* the budget gate.** This is the architectural enforcement
  of "captions path bypasses budget" — not a runtime conditional in
  the gate. `mypy`'s narrowing means the provider call is only ever
  reached with `PreparedMedia` (the type narrowing is automatic on
  the `else` branch).
- **The provider abstraction stays typed on `PreparedMedia`, not
  `PreparedSource`.** This is a deliberate choice: the captions path
  must never reach a provider. Typing `transcribe(media: PreparedMedia)`
  means `mypy` catches accidental "let's pass a PreparedTranscript to
  AssemblyAI" misuse at compile time.
- **`caption_type` is on `PreparedTranscript.extra`, not as a typed
  field.** Keeps the dataclass source-agnostic — a future
  `OtterSource` or `NotebookLMImportSource` won't carry a
  meaningless `caption_type` field. The formatter looks for it only
  when `media.kind == "youtube_captions"`.
- **Tenacity retries only network-layer exceptions.** The library
  exceptions (`TranscriptsDisabled`, `IpBlocked`, ...) are
  deterministic in a single run — retrying them just wastes 7 seconds.
  Two counter-tests in `test_youtube_source.py` assert that
  `TranscriptsDisabled` and `IpBlocked` are *not* retried.
- **oembed is fail-soft on every path.** 401 / 403 / 404 / timeout /
  malformed JSON / missing key / hostile title all return `None` so
  the captions path is never blocked by oembed. DEBUG log only —
  oembed failure is a normal outcome on a non-trivial fraction of
  videos, not WARN-worthy.
- **The no-captions error message is the user-facing contract.**
  Names what failed in two clauses ("creator disabled OR no
  auto-generated"), points at issue #21 with the real GitHub URL,
  and offers a copy-paste yt-dlp workaround that runs on Phase 1's
  local-ASR path today. The CLI test (`test_captions_no_captions_exits_2_with_documented_message`)
  asserts on the literal phrases so a regression on the message wording
  breaks the suite, not just the user.
- **`youtube-transcript-api` is pinned to `>=1.0,<2.0` for a reason.**
  The 1.0 rewrite moved from static `get_transcript()` to
  instance-method `YouTubeTranscriptApi().fetch()`. The verbatim
  reference section in the spec pins this API surface at retrieval
  date 2026-05-12; if the pin range is bumped, the spec section
  must be re-verified in the same PR (per CLAUDE.md vendor-API
  guardrail).

## Tests

- **42 new tests** in `tests/unit/test_youtube_source.py` covering
  URL parsing (10 accepted forms + 7 rejected + 1 too-long), caption
  resolution (manual preferred, auto fallback, no tracks raises),
  segment mapping (ms conversion + last-segment duration), oembed
  (200 happy path + 401/403/404/500/timeout/missing-key/malformed-json/
  hostile-title), retry (transient retried, deterministic not
  retried, 3-attempt exhaustion).
- **6 new CLI integration tests** in `tests/unit/test_cli.py`
  covering the happy path (provider + budget NOT called),
  `--budget free` allowed, `TranscriptsDisabled` exit 2 with the
  documented message, `IpBlocked` exit 3, `--language` ignored with
  INFO log, no-title fallback to video-ID stem.
- **5 new formatter tests** in `tests/unit/test_markdown_formatter.py`
  covering captions frontmatter (provider/model/caption_type/diarized/
  speakers/assemblyai_job_id all set correctly), body summary
  showing `youtube-captions (manual|auto)`, video-ID fallback when
  no title, regression that AssemblyAI sources keep their existing
  frontmatter without `caption_type`.
- **2 new Protocol/sibling tests** in `tests/unit/test_provider_types.py`
  + 5 new dispatch tests in `test_source_dispatch.py`.
- Total: 261 unit tests pass; ruff + mypy clean.

## Interview angle

- **Story type:** clean Protocol-and-sibling refactor of a contract
  that had been extended additively twice already, plus a
  free-by-construction implementation path (no paid API call).
- **One-sentence hook:** "Shipped a YouTube source that's $0 by
  construction by branching on a `PreparedTranscript` sibling
  dataclass *before* the budget router fires."
- **Architectural decisions captured:**
  - When does additive contract extension stop being additive?
    Three modes is one more than two; the `PreparedMedia` dataclass
    name was about to lie. Refactor to a Protocol + sibling.
  - How do you make "captions bypass budget" architectural, not
    procedural? Type the provider on the concrete `PreparedMedia`,
    not the Protocol. mypy enforces the constraint at compile time.
  - When does a tenacity wrap help vs hurt? Retry network-layer
    exceptions; never retry deterministic application errors.
    Two counter-tests lock the boundary.
- **Cost-shape decision worth retelling:** The free path (captions)
  covers the common YouTube case; audio fallback (Slice 2) only
  earns its complexity on the long tail. Frontmatter records
  `caption_type` so downstream tooling (NotebookLM, Obsidian) can
  treat manual captions, auto captions, and ASR transcripts
  differently.
- **Pointer:** [`interview-prep.md`](../interview-prep.md) — the
  PreparedMedia DTO boundary design story now extends to cover this
  Protocol-and-sibling refactor.

## Further reading

- [`pr-030-youtube-captions-source-spec.md`](pr-030-youtube-captions-source-spec.md) — the spec that drove this implementation.
- [`pr-017-drive-source-passthrough-impl.md`](pr-017-drive-source-passthrough-impl.md) — the prior SDD impl PR; this one mirrors its structure.
- [`pr-013-prevent-vendor-api-shape-regressions.md`](pr-013-prevent-vendor-api-shape-regressions.md) — the CLAUDE.md vendor-API guardrail this impl follows.
- [`specs/2026-05-12-youtube-captions-source/`](../../../specs/2026-05-12-youtube-captions-source/) — the spec triple (requirements / plan / validation).
