# PR #15 — Feature spec: Drive Source (URL Passthrough)

**Merged:** TBD  |  **Branch:** `feature/drive-source-passthrough-spec`  |  **Codex review:** TBD
**Journey entry:** [`../journey.md#pr-15--feature-spec-drive-source-url-passthrough`](../journey.md#pr-15--feature-spec-drive-source-url-passthrough)

## The problem in one paragraph

Slice 1 (PR #12) shipped local-file transcription. Slice 2 is the
second source: Google Drive videos the user has already shared as
"anyone with link can view." The straight-line solution from
PLAN.md's Phase 4 was OAuth + `google-api-python-client` download,
but the user surfaced a working `curl` early in the brainstorm that
points at a fundamentally cheaper path: pass the public Drive
download URL straight to AssemblyAI's `audio_url` field and let
AssemblyAI fetch it server-to-server. No OAuth. No download. No
upload. ~5–10× faster on a 60-min file. The risk of jumping straight
into implementation without a committed spec is the same as PR #10's
risk: drift between the brainstorm and the code. SDD says write the
spec, commit it, *then* implement.

## What changed (high level, not file-by-file)

- New folder `specs/2026-05-04-drive-source-passthrough/` with three files:
  - `requirements.md` — Goal / Non-goals / 10 numbered scenarios /
    constraints + decisions / **`## Reference calls (verbatim)`**
    section with the user's actual `curl` pasted byte-for-byte /
    output frontmatter contract / F-contract status / dependencies
    (none).
  - `plan.md` — 10 numbered task groups (F2 contract extension,
    `DriveSource`, source dispatch, provider passthrough branch,
    Drive-variant budget gate, CLI wiring, formatter handling
    `local_path=None`, tests, teaching artifacts, exit gate).
  - `validation.md` — 7 success criteria with required evidence,
    27 test cases, 8 edge cases, definition of done.
- Per-PR teaching artifacts: this explainer, the journey entry, the
  prs/README index row.

## Why this approach

The four user-facing decisions the brainstorm settled, in the order
they were asked:

1. **Auth model — public URL passthrough only.** Matches the
   working `curl` exactly. OAuth + private-file support deferred to
   Slice 3. The user explicitly said "A first, B in future
   probably."
2. **URL forms — both `drive://FILE_ID` and full Drive URL.** Humans
   paste full URLs from the browser; scripts use `drive://`. ~10
   lines of regex parsing, both paths converge to the same file ID.
3. **Frontmatter `title` — `--title` flag, defaults to file ID.** No
   OAuth = no programmatic filename access. `Content-Disposition`
   scraping was offered as an alternative but defers because Drive's
   >100 MB interstitial breaks the simple HEAD-request approach. User
   knows the title at invocation time anyway.
4. **Cost pre-estimate — skipped for Drive sources.** No local file
   = no `ffprobe`. Soft cap silenced; both *hard* gates (key
   configured + budget != free) still fire. Honest "no estimate"
   beats wrong number.

The single architectural decision the brainstorm settled is the F2
contract change: `PreparedMedia.local_path` becomes `Path | None`,
new `remote_url: str | None = None` field lands. Validation:
exactly one must be set. The provider branches once on
`if media.remote_url`. Polling, retry, formatter all reuse Slice 1's
plumbing unchanged. Backward-compatible because the new field
defaults to `None`.

## What a reviewer should notice

- **First feature spec to fill in PR #13's
  `## Reference calls (verbatim)` section.** This is the dogfood
  test of the prevention-layer template — the user's actual working
  `curl` is pasted at the top of `requirements.md` so the implementer
  copies from it byte-for-byte rather than paraphrasing. PR #13's
  premise was "wrong vendor API shape because the implementation
  paraphrased rather than copied"; this spec proves the pattern is
  followable in practice.
- **Zero new dependencies.** No `google-api-python-client`, no
  `google-auth-oauthlib`, no `requests.get` against Drive itself
  (we never download). The Drive download URL is a plain string we
  hand to AssemblyAI.
- **PLAN.md Phase 4 said OAuth.** This spec's "Why this approach"
  section makes the deviation explicit and pins OAuth to Slice 3.
  Phase 4 in `specs/roadmap.md` will move from `pending` →
  `partial — public-link passthrough only (Slice 2). OAuth + private
  files deferred to Slice 3.` when this slice's *implementation* PR
  merges.
- **The F2 contract change is genuinely additive.** Existing
  `LocalSource.prepare(...)` callsites compile and test green
  unchanged because the new `remote_url` field has a default of
  `None` and `local_path` keeping its current type would still
  validate. No callsite churn outside `sources/base.py` itself and
  the new `DriveSource`.

## Interview angle

- **Story type:** SDD discipline + cheapest-acceptable-architecture
  decision under spec.
- **One-sentence hook:** "Picked URL-passthrough over OAuth+download
  for the second source after a brainstorm that surfaced a working
  curl proving AssemblyAI accepts public Drive URLs directly —
  shipped a 0-new-dependency, ~5×-faster path while pinning the
  OAuth work as Slice 3 for when private-file support is actually
  needed."
- **Pointer:** the four-decision brainstorm walks through the
  question-by-question logic; the deferred OAuth slice is explicitly
  documented rather than implicitly skipped.

## Further reading

- [`pr-013-prevent-vendor-api-shape-regressions.md`](pr-013-prevent-vendor-api-shape-regressions.md) — the prevention layer this spec is the first to dogfood.
- [`pr-010-assemblyai-mvp-slice-1-spec.md`](pr-010-assemblyai-mvp-slice-1-spec.md) — the spec PR pattern this PR follows.
- [`pr-012-assemblyai-mvp-slice-1-impl.md`](pr-012-assemblyai-mvp-slice-1-impl.md) — Slice 1's implementation that this slice's F2 contract change extends.
- [`../../../specs/2026-05-04-drive-source-passthrough/`](../../../specs/2026-05-04-drive-source-passthrough/) — the spec triple itself.
