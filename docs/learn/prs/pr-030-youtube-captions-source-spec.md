# PR #30 — Feature spec: YouTube Source (Captions Passthrough)

**Merged:** 2026-05-12  |  **Branch:** `feature/youtube-captions-source-spec`  |  **Codex review:** 2 P2 findings, both addressed
**Journey entry:** [`../journey.md#pr-30--feature-spec-youtube-source-captions-passthrough`](../journey.md#pr-30--feature-spec-youtube-source-captions-passthrough)

## The problem in one paragraph

Phase 2 was scoped in PLAN.md as a single "add YouTube support" step
that downloads audio with yt-dlp and runs it through the local ASR
path. The brainstorm for issue #20 split that into two slices: most
YouTube videos already expose captions YouTube fetched or generated
themselves, and a captions-only path is **$0 by construction** — no
audio bandwidth, no ASR call. yt-dlp audio fallback (Slice 2) only
earns its complexity on the long tail of captionless videos.
SDD says write the spec, commit it, review it, *then* implement.

## What changed (high level, not file-by-file)

- New folder `specs/2026-05-12-youtube-captions-source/` with three files:
  - `requirements.md` — Goal / Non-goals / 12 scenarios / constraints
    + 13 feature-specific decisions / **`## Reference calls (verbatim)`**
    with the current `youtube-transcript-api` API surface (ctx7-fetched
    2026-05-12, retrieval date pinned) AND the real `curl`-verified
    YouTube oembed response shape / output frontmatter contract /
    F-contract status / dependencies (one new runtime: `youtube-transcript-api`).
  - `plan.md` — 11 numbered task groups (F2 Protocol extension →
    `TranscriptResult` generalization → `YouTubeSource` → oembed →
    tenacity retry → dispatch → CLI branch → formatter changes →
    tests → teaching artifacts → exit gate).
  - `validation.md` — 9 success criteria with required evidence,
    72 test cases, 12 edge cases, definition of done.
- Per-PR teaching artifacts (this explainer + journey entry +
  prs/README index row land in the impl PR per the SDD cadence —
  the spec PR is documentation about a not-yet-shipped slice).

## Why this approach

Seven design questions settled during the brainstorm, in the order
they were asked. Each one decisively narrows scope or commits to a
specific user-facing behaviour.

1. **Caption types — manual + auto-generated, exclude auto-translated.**
   Auto-translated tracks layer MT errors on top of ASR errors;
   they're worse than just running Slice 2's local ASR on the
   original audio. Skipping them removes one branch from the
   resolver and one whole category of bad output. Recorded in
   the frontmatter as `caption_type: manual|auto`.

2. **Track selection — original-language-first.** The library's
   `ytt_api.fetch(video_id)` defaults to English (verified via the
   ctx7 docs fetch), which is wrong for non-English videos. Our
   resolver iterates `transcript_list` manually, prefers
   `not t.is_generated` (manual) over `t.is_generated` (auto),
   never calls `.translate()`. The `--language` flag is a Slice 1
   *ASR override* — meaningless for pre-transcribed captions — so
   it's silently ignored with an INFO log on captions sources.

3. **Source contract — `PreparedSource` Protocol + `PreparedTranscript`
   sibling.** F2 had already been extended additively twice (Drive
   Slice 2 added `remote_url`); a third extension to `PreparedMedia`
   for "transcript is already done" would make the "media" name
   dishonest. The cleaner refactor: introduce a `PreparedSource`
   Protocol that captures the five shared metadata fields, leave
   `PreparedMedia` unchanged, add a `PreparedTranscript` sibling
   dataclass with the finished `TranscriptResult` inline. The
   provider abstraction stays typed on the concrete `PreparedMedia`
   — `mypy` enforces that the captions path never reaches a provider
   call. The user explicitly preferred this over a smaller
   `PreparedMedia.prepared_transcript: TranscriptResult | None`
   extension because "cleaner even if bigger PR."

4. **Frontmatter — additive `caption_type` field; reads from
   `result.provider` and Optional `model`/`job_id`.** The formatter
   was hardcoded to `provider: assemblyai`. Generalizing it to read
   from `TranscriptResult.provider` (and to render `model` /
   `assemblyai_job_id` as YAML `null` when None) is the smallest
   formatter change that unlocks both captions and any future
   provider. Frontmatter field name `assemblyai_job_id` stays for
   downstream-parser schema stability; Phase 5 generalizes to
   `provider_job_id`.

5. **Library reliability — version pinning, no cache, narrow retry,
   typed error matrix, ToS posture.** `youtube-transcript-api` is an
   unofficial scraper with several breaking releases (the 1.0
   rewrite moved from static `get_transcript()` to instance-method
   `YouTubeTranscriptApi().fetch()`). The spec pins `>=1.0,<2.0`
   and quotes the ctx7-fetched API surface verbatim. Caching is
   deferred (F3 doesn't apply to caption fetches; the cost / value
   trade-off doesn't pay). Tenacity retries only network-layer
   exceptions (`requests.Timeout`, `requests.ConnectionError`);
   `CouldNotRetrieveTranscript` subclasses are deterministic in a
   single run and propagate immediately. Each subclass maps to a
   specific CLI exit code with a specific user-facing message.

6. **Budget gate — bypassed entirely on captions sources.** Under
   Option 2 (PreparedTranscript), the CLI branches on
   `isinstance(prepared, PreparedTranscript)` *before* reaching the
   budget router. `--budget free` is allowed on captions (it's $0,
   honestly). The Drive-vs-captions asymmetry under `--budget free`
   is documented in the spec so future readers don't think it's a bug.

7. **No-captions error wording.** Exit 2 with a message that names
   what failed ("creator disabled captions OR no auto-generated
   track is available"), points at issue #21 with the real GitHub
   URL, and offers a copy-paste `yt-dlp + uv run ssm-transcriber transcribe`
   workaround that uses Phase 1's free local-ASR path today.

The architectural insight worth highlighting is **decision #3**.
F2's "additively extend `PreparedMedia` for each new source mode"
worked twice but was about to break at three modes — "media that
needs ASR via upload" + "media that needs ASR via URL passthrough"
+ "transcript that needs no ASR at all" is a tagged union of three,
and the third entry mismatches the "media" name. The Protocol +
sibling pattern is the standard refactor for that shape: keep the
existing dataclass intact, define a Protocol that captures the
intersection, and add a new dataclass for the new mode. Python's
structural `Protocol` makes this clean — no `inherits` declarations
needed; both dataclasses satisfy the Protocol because they expose
the five required attributes. The cost is one new dataclass and a
single `isinstance` check at the CLI's pipeline branch; the benefit
is that future caption-emitting sources (Otter export, NotebookLM
saved transcripts, …) reuse `PreparedTranscript` with no contract
churn.

## Codex review

Two P2 findings, both addressed before merge:

1. **Scenario 1 said oembed fetch runs "in parallel"; the binding F1
   sync-only constraint says synchronously after captions fetch.**
   Internal contradiction. Reworded scenario 1 to match the
   constraint.

2. **Decisions table said "Source dispatch returns `PreparedSource`",
   but the existing dispatcher returns a source class.** Wrong by
   the existing CLI/test contract. Reworded: `prepare()` returns
   `PreparedSource`; `resolve_source()` keeps its existing "return
   the source class" shape with the union widened to include
   `type[YouTubeSource]`.

Both findings were genuine internal inconsistencies — Codex caught
them correctly. Spec PR addressed inline (commit `3832dce`) and the
fix landed in the same PR before merge.

## What a reviewer should notice

- **The spec is a contract, not narration.** Every "decision" row in
  §"Constraints" has a Rationale column that names *why* the
  alternative was rejected — readable in 90 seconds.
- **The verbatim reference section pins the library API at retrieval
  date 2026-05-12.** Per CLAUDE.md's vendor-API guardrail (the
  PR #12 lesson), API shapes must be copied byte-for-byte, never
  paraphrased from memory. ctx7 docs fetch + a real `curl` to oembed
  cover both.
- **The F-contract status table is a one-line audit** for each F1–F8
  contract: this slice extends F2 (via Protocol + sibling), bypasses
  F4 (no provider call so no budget gate), defers F3 (no cache),
  reuses F5 / F8 unchanged, F6 / F7 N/A.
- **The error matrix maps each library exception to a specific exit
  code and message.** No catch-all "something went wrong" path.
- **The "supply a single video URL" rejection list is explicit.**
  Playlist URLs, channel URLs, channel-handle URLs, and the YouTube
  homepage are rejected at parse time with a specific message;
  reject-not-swallow keeps the failure mode loud.

## Interview angle

- **Story type:** spec-driven evolution of a contract that's already
  been extended once before — recognizing the smell of a third
  extension and refactoring to the cleaner shape *as a deliberate
  design decision*, not a code-review regret.
- **One-sentence hook:** "I refactored the source contract from a
  three-mode tagged union to a Protocol-plus-sibling because the
  existing dataclass name ('media') was about to lie about its
  contents."
- **Architectural decisions captured:**
  - When does additive contract extension stop being additive?
    Answer: when the third mode forces the existing fields to
    semantically mean different things.
  - How do you keep the provider abstraction honest when one source
    bypasses it? Answer: type the provider on the concrete dataclass
    (`PreparedMedia`), not the Protocol (`PreparedSource`) — mypy
    enforces the architectural constraint at compile time.
- **Pointer:** see [`interview-prep.md`](../interview-prep.md) — the
  "PreparedMedia DTO boundary design" story now extends to cover
  this Protocol-and-sibling refactor.

## Further reading

- [`specs/2026-05-12-youtube-captions-source/requirements.md`](../../../specs/2026-05-12-youtube-captions-source/requirements.md) — the spec being shipped here.
- [`pr-015-drive-source-passthrough-spec.md`](pr-015-drive-source-passthrough-spec.md) — the prior SDD spec PR; this one mirrors its structure.
- [`pr-013-prevent-vendor-api-shape-regressions.md`](pr-013-prevent-vendor-api-shape-regressions.md) — the CLAUDE.md `## Reference calls (verbatim)` guardrail this spec follows.
