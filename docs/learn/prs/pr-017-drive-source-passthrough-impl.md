# PR #17 — Implementation: Drive Source (URL Passthrough)

**Merged:** TBD  |  **Branch:** `feat/drive-source-impl`  |  **Codex review:** TBD
**Journey entry:** [`../journey.md#pr-17--implementation-drive-source-url-passthrough`](../journey.md#pr-17--implementation-drive-source-url-passthrough)

## The problem in one paragraph

PR #15 committed the spec triple for Slice 2 ("Google Drive video shared
as anyone-with-link → AssemblyAI URL passthrough → enriched Markdown").
PR #16 committed the execution plan (plus two review rounds — one inline
and one via the formal `pr-review-toolkit` agents — that surfaced 18
findings, 8 of which were applied to the plan as safety-critical fixes
before any code landed). This PR is the implementation against the
twice-reviewed plan. It is the *second* feature loop the repo runs
end-to-end under SDD, and it is the first to run the new "plan PR
sandwiched between spec and impl" cadence the user adopted after PR #12
landed in one large impl PR.

## What changed (high level, not file-by-file)

Eight implementation commits land the slice in the order of the
execution plan's task groups, plus this teaching-artifacts commit:

1. **F2 contract extension + `SourceInputError`.** `PreparedMedia`
   now has `local_path: Path | None` and `remote_url: str | None`
   with a `__post_init__` XOR invariant. `SourceInputError(ValueError)`
   distinguishes user-input failures (bad URI, missing file) from
   producer-side `PreparedMedia` invariant violations so the CLI
   doesn't leak invariant messages to end users (review finding I7
   from the formal review).
2. **Drive URL parser.** `_extract_file_id` accepts the five URL forms
   documented byte-for-byte in `requirements.md` §"Reference calls
   (verbatim)". Uses `re.fullmatch` not `re.match + $` (the latter
   matches before a final newline by default — `"abc\n"` would slip
   past validation; the `_rejects_drive_uri_with_trailing_newline`
   test locks that down).
3. **`DriveSource.prepare` + `LocalSource.prepare(title=...)`.**
   `DriveSource` wraps the parser and produces `PreparedMedia` with
   `local_path=None` and `remote_url=<canonical download URL>`.
   `LocalSource.prepare` gains the same `title=` keyword so the CLI
   can pass `--title` through both source types via the same kwarg
   — avoids the post-construction `dataclass.replace` mutation an
   earlier review iteration of the plan had used.
4. **`resolve_source` dispatcher.** Pattern-match URI shape →
   `DriveSource` for `drive://` and `https?://drive.google.com/`,
   `LocalSource` for no-scheme paths, `SourceInputError` for any
   other `://`. Reject-not-swallow: a YouTube URL today raises a
   loud "URI scheme not supported" rather than silently routing to
   `LocalSource` and surfacing as "file not found."
5. **Provider `audio_url` passthrough branch.** `transcribe()` now
   takes `media: PreparedMedia` instead of `wav_path: Path`; branches
   on `media.remote_url`. Passthrough path skips `/upload` entirely
   and POSTs `audio_url=<media.remote_url>` to `/transcript`. The
   body-shape `responses.matchers.json_params_matcher` per CLAUDE.md
   guardrail (PR #13) catches future field-name regressions.
6. **`--title` sanitization.** `_validate_title` returns the display
   form (whitespace stripped at edges, internal preserved) for YAML
   frontmatter; `_title_to_stem` collapses internal whitespace to `-`
   for the filename stem. Both helpers are split because the YAML
   form ("Session 17") and the filename stem ("Session-17") must
   never get accidentally swapped. `atomic.write_text_atomic` creates
   parent directories on demand, so unsanitized `--title "../foo"`
   would let a user write outside `settings.output_dir` — the
   parametrised `_rejects_unsafe_characters` test locks down `/`,
   `\`, NUL, `..`, leading `.`, and the empty case.
7. **Markdown formatter handles `local_path=None`.** `_source_uri`
   returns `media.original_uri` (already `drive://FILE_ID`) for
   non-local sources; `render()` falls back to
   `media.extra["drive_file_id"]` for the title when neither
   `--title` nor `local_path.stem` is available. Both fallbacks are
   **fail-loud** (review I4 + I6): missing `drive_file_id` raises
   `KeyError`; impossible `kind=='local' + local_path=None` raises
   `ValueError`. No more silent "untitled-DATE.md" outputs from
   producer bugs.
8. **CLI integration (largest commit).** `--title` flag,
   `resolve_source` dispatch, Drive-variant budget gate via the new
   `core/budget.py:check(cost_summary=...)` parameter (single-sources
   Gate 1 + Gate 2 in the gate function), output filename derivation,
   and the C1 fix: `dataclasses.replace(media, local_path=wav_path)`
   after `extract_audio` so the provider uploads the canonical
   16 kHz mono WAV — not the original `.mp4`. Without this swap
   AssemblyAI accepts any audio container, so the regression would
   be invisible past mocks but silently break Slice 1's
   "extract → normalised WAV → upload" contract. The
   `test_local_path_uploads_extracted_wav_not_source_file` test
   records what reaches the provider's `transcribe()` call so a
   future refactor that drops the swap breaks the suite.

## Why this approach

The five user-facing decisions and one architectural decision settled
during the brainstorm and spec PRs (#15) are recorded there; this
explainer focuses on the *implementation-phase* decisions and learnings.

The single biggest implementation-phase decision was **how to thread
the WAV path back into `media` after `extract_audio`**. The plan as
originally written (and as the formal review-pr agents flagged in
finding C1) shipped the regression where `media.local_path` stayed
pointing at the user's source file (`.mp4`) and the provider uploaded
that instead of the workspace-extracted WAV. The fix candidates were
(a) `dataclasses.replace`, (b) refactor `extract_audio` to return a
new `PreparedMedia`, (c) thread the WAV separately. (a) won because
this is genuinely an intra-pipeline transform (the CLI owns the
canonical media transform after audio extraction), unlike the
title-injection use of `dataclass.replace` that an earlier review
iteration removed for being a cross-cutting concern that should have
been a `Source.prepare(title=...)` kwarg. The conceptual difference is
that the source layer cannot know the WAV path at `prepare()` time
(it's produced downstream by `extract_audio`), whereas title was
something the CLI knew at prepare-time.

## What the formal review-pr round caught (PR #16 plan PR)

Five `pr-review-toolkit` agents reviewed the plan in parallel:
`code-reviewer`, `pr-test-analyzer`, `silent-failure-hunter`,
`type-design-analyzer`, `comment-analyzer`. They surfaced 18 findings;
the safety-critical 8 were applied to the plan before this PR opened:

- **C1 (code-reviewer):** the WAV-vs-source upload regression
  described above.
- **I1 (pr-test-analyzer):** validation case 18 (polling status
  `error` on the `remote_url` branch) had no test; added.
- **I2:** validation case 20's per-minute/dashboard notify text had
  no production assertion; added inside `test_drive_happy_path_with_title`.
- **I3:** validation case 21 (Gate 1 fail on Drive sources) had no
  test; added `test_drive_no_api_key_still_blocks_at_gate_1`.
- **I4 + I5 (silent-failure-hunter):** silent `media.extra.get(...,
  "untitled")` fallbacks in formatter and CLI; replaced with `[]`
  access so producer-side bugs raise `KeyError` loudly rather than
  silently producing `untitled-DATE.md` files.
- **I6:** `_source_uri`'s wrong-shape silent fallback for
  invariant-violating local media; added explicit `raise ValueError`.
- **I7:** broad `except ValueError` in CLI conflated user-input
  ValueErrors with `PreparedMedia` invariant violations; introduced
  `SourceInputError(ValueError)` subclass and changed the catch to
  the more specific type.

The **8 deferred** findings (I8 + S1 + S2 type-design refactors,
S3 + S4 + S5 polish) are documented in PR #16 and queued for a
follow-up review round; nothing is safety-critical.

## What a reviewer should notice

- The PR is **medium-sized** (8 commits + this teaching one + roadmap
  + runbook), each commit maps 1:1 to a plan task group, so
  commit-by-commit review remains feasible.
- **F2 contract change is genuinely additive.** Existing
  `LocalSource.prepare(...)` callsites continue to work because the
  new `remote_url` field defaults to `None` and `local_path` keeps
  its position-friendly slot. No callsite churn outside
  `sources/base.py` itself + the new `DriveSource`.
- **Zero new dependencies.** No `google-api-python-client`, no
  `google-auth-oauthlib`, no `requests.get` against Drive itself.
  The Drive download URL is a plain string we hand to AssemblyAI's
  `audio_url` field — exactly mirroring the working `curl` in
  `requirements.md` §"Reference calls (verbatim)".
- **Body-shape `json_params_matcher` is wired in** for the new
  `audio_url`-bearing POST (PR #13's vendor-API-shape regression
  prevention layer dogfooded in production).
- **Both Gates fire on Drive sources.** `core/budget.py:check`'s
  new `cost_summary=` parameter overrides the cost-estimate notify
  line (we have no local duration to estimate against) without
  short-circuiting Gate 1 or Gate 2. Single-sources the gate logic
  in `core/budget.py` instead of duplicating it into the CLI.
- **The C1 fix has a regression test that records what reaches the
  provider.** `test_local_path_uploads_extracted_wav_not_source_file`
  uses a `_RecordingProvider` mock that captures `media` arguments
  and asserts the WAV path landed there, not the source path.
- **Path-traversal protection.** `_validate_title` rejects `/`, `\`,
  NUL, `..`, and leading `.`, parametrised across 6 test cases plus
  an empty-after-strip rejection.
- **Reject-not-swallow at dispatch is enforced and tested** for
  YouTube, generic-https, and `s3://` URIs.
- **The manual runbook** was executed against a real Drive file the
  user shared as anyone-with-link (~$X.XX, fill in actual cost from
  the AssemblyAI dashboard at PR finalisation time). Drive sharing
  setting must be "anyone with link" — Slice 3's OAuth + private
  files is explicitly deferred.

## Interview angle

- **Story type:** SDD execution discipline + multi-stage review
  pipeline + cheapest-acceptable-architecture decision under spec.
- **One-sentence hook:** "Implemented Drive source URL passthrough
  end-to-end across an 8-task TDD plan that itself went through two
  review rounds (one inline, one via parallel `pr-review-toolkit`
  agents) before any code landed; the formal review caught a
  silent-but-invisible WAV-vs-source upload regression that would
  have shipped through 135 unit tests undetected — exactly the kind
  of finding that justifies the plan-PR-sandwich cadence."
- **Pointer:** the "What the formal review-pr round caught" section
  walks through the 8 safety-critical findings; the C1 finding alone
  is a concrete artifact of why "tests pass" is not evidence that
  the contract is preserved.

## Further reading

- [`pr-015-drive-source-passthrough-spec.md`](pr-015-drive-source-passthrough-spec.md) — the spec triple this PR implements.
- [`pr-013-prevent-vendor-api-shape-regressions.md`](pr-013-prevent-vendor-api-shape-regressions.md) — the body-shape mock guardrail this PR's new `audio_url` POST honours.
- [`pr-012-assemblyai-mvp-slice-1-impl.md`](pr-012-assemblyai-mvp-slice-1-impl.md) — Slice 1's implementation that this PR's F2 contract change extends.
- [`../../../specs/2026-05-04-drive-source-passthrough/`](../../../specs/2026-05-04-drive-source-passthrough/) — the spec triple + execution plan.
