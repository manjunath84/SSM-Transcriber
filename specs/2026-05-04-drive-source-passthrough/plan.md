# Plan — Drive Source (URL Passthrough)

> Numbered task groups. Each group is a coherent chunk that can be
> implemented and reviewed together. Specific function signatures,
> field names, and other implementation details are deliberately *not*
> specified here — the implementer decides those during the build,
> consistent with `specs/tech-stack.md` conventions.

## 1. F2 contract extension — `PreparedMedia.remote_url`

Extend `src/transcriber/sources/base.py`:

- `local_path: Path` → `local_path: Path | None`.
- New `remote_url: str | None = None`.
- `__post_init__` validation: **exactly one** of `local_path` /
  `remote_url` must be set. Both unset → `ValueError`. Both set →
  `ValueError`. (Mirrors the `Segment.__post_init__` pattern from
  Slice 1.)
- All existing `LocalSource.prepare(...)` callsites continue to work
  unchanged — they pass `local_path=...` and the default
  `remote_url=None` keeps the validation happy.

Tests for the validation in `tests/unit/test_provider_types.py` (where
`Segment.__post_init__` tests live), or a new
`tests/unit/test_prepared_media.py` if that file feels too crowded.

## 2. `DriveSource` and URL-form parsing

New `src/transcriber/sources/google_drive.py`:

- `DriveSource.prepare(uri, workspace) -> PreparedMedia`.
- Accept the five URL forms documented in
  `requirements.md` §"Reference calls (verbatim)". Extract the file ID
  via regex.
- Build the canonical public-download URL:
  `https://drive.google.com/uc?export=download&id=<FILE_ID>`.
- Return `PreparedMedia(kind="google_drive",
                         original_uri=f"drive://{file_id}",
                         local_path=None,
                         remote_url=<public download URL>,
                         title=None,                    # CLI fills in from --title
                         duration_seconds=None,
                         workspace=workspace,
                         extra={"drive_file_id": file_id})`.
- Unparseable input (no extractable ID, non-Drive host, malformed
  `drive://`) → `ValueError`.

## 3. Source dispatch

Update `src/transcriber/sources/__init__.py` (or create
`sources/dispatch.py`):

- `resolve_source(uri: str)` — picks `LocalSource` or `DriveSource`
  based on URI scheme:
  - `drive://` or starts with `https://drive.google.com/` →
    `DriveSource`.
  - otherwise → `LocalSource`.
- Future-proof: when YouTube / OAuth-Drive land, they slot in by
  pattern.

## 4. Provider passthrough branch

Update `src/transcriber/providers/assemblyai.py` and
`src/transcriber/providers/base.py`:

- Change `transcribe()` signature to take a single `media: PreparedMedia`
  argument (or keep `wav_path` and add `audio_url`; implementer's
  call). The CLI was already constructing `PreparedMedia` — passing it
  whole is the cleanest seam.
- Internally:
  - If `media.remote_url`: skip `_upload`. POST `/transcript` with
    `audio_url=media.remote_url`. The same body-shape match as today
    plus the `audio_url` field; no other create-transcript fields
    change.
  - Else: existing path — `_upload(media.local_path)` then
    `_create_transcript(upload_url=...)`.
- Polling loop, segment build, and `TranscriptResult` construction
  unchanged.
- `_with_retry` decorator already wraps both `_upload` and
  `_create_transcript`; no new tenacity decorations needed.

## 5. Budget gate — Drive variant

Update `src/transcriber/cli.py` only (no change to
`core/budget.py`):

- Before calling `budget_check`, branch on `media.remote_url`:
  - Drive path: skip the cost estimate; pass `cost_usd=0.0` (or a
    sentinel) and a notify message: "AssemblyAI bills per-minute
    against URL passthrough; exact cost in dashboard." Soft cap
    silenced (don't print the soft-cap line).
  - Local path: existing call with the `ffprobe`-derived estimate.
- Both Gate 1 and Gate 2 still fire via the existing `budget_check`
  (the function gets `key_configured`, `budget`, etc.; the only
  difference is what we pass for `cost_usd`).
- Implementation choice: smallest change is a tiny CLI-local helper
  that wraps `budget_check` with the Drive-specific notify. Don't
  push the source-kind branch into `budget.py` — that would couple
  the gate function to source types and the abstraction is cleaner
  if the CLI handles the "no pre-estimate" framing.

## 6. CLI wiring

Update `src/transcriber/cli.py`:

- Add `--title <str>` flag (Annotated, default `None`).
- Replace `LocalSource.prepare(source, workspace)` with
  `resolve_source(source).prepare(source, workspace)`.
- After `prepare`, branch on `media.remote_url`:
  - Drive path: skip `extract_audio`; thread `--title` into
    `media.title` (or carry it separately into the formatter and
    output filename). Run the Drive variant of the budget gate
    (above).
  - Local path: existing `extract_audio` + budget gate.
- Output filename derivation:
  - If Drive AND `--title` set: `{title}-{date}.md`.
  - If Drive AND no `--title`: `{file_id}-{date}.md` (file ID from
    `media.extra["drive_file_id"]`).
  - If Local: existing `media.local_path.stem` behaviour.
- Whitespace in `--title` → `-` in the filename; other characters
  round-trip. (Existing `atomic.resolve_collision` handles the
  filename-collision suffix logic regardless of source.)

## 7. Markdown formatter — handle `local_path=None`

Update `src/transcriber/formatters/markdown.py`:

- `_source_uri(media)` already special-cases `kind == "local"`.
  Add a branch for `kind == "google_drive"`: return
  `media.original_uri` (which is already `drive://FILE_ID`).
- `title` derivation in `render()`:
  `media.title or media.local_path.stem` becomes
  `media.title or (media.local_path.stem if media.local_path else
  media.extra["drive_file_id"])`.
- The body's summary blockquote uses `media.original_uri` as the
  source reference — already source-agnostic.

## 8. Tests

Unit tests with mocked HTTP (`responses`) cover all the paths in
`validation.md` §"Test cases":

- New `tests/unit/test_google_drive.py` — URL-parse cases; invalid
  URLs raise `ValueError`; returned `PreparedMedia` shape.
- New `tests/unit/test_source_dispatch.py` — `resolve_source` picks
  the right source per scheme.
- Extend `tests/unit/test_assemblyai_provider.py` — body-shape mock
  asserting POST `/transcript` includes `audio_url=...` AND no
  `/upload` call fires; existing local-path tests still pass.
- Extend `tests/unit/test_cli.py` — Drive happy path, `--title`
  threaded, `--budget free` rejection on Drive sources.
- Extend `tests/unit/test_provider_types.py` (or new
  `test_prepared_media.py`) — `PreparedMedia` validation.
- Extend `tests/unit/test_markdown_formatter.py` — render against a
  Drive `PreparedMedia` (no `local_path`); body-and-frontmatter
  golden output.

Manual: extend `tests/manual/end_to_end.md` with a second scenario
(Drive URL passthrough) — single real run, ~$0.60 against an
already-shared Drive file the user has on hand. Do NOT add real
Drive fixtures to CI.

## 9. Per-PR teaching artifacts

Once implementation lands and before opening the PR:

- Draft `docs/learn/prs/pr-NNN-drive-source-passthrough-impl.md` using
  the repo's explainer template. Highlight: (a) why URL passthrough
  beat OAuth+download for the user's workflow today; (b) the F2
  contract extension as the smallest seam; (c) this is the first
  feature spec to fill in PR #13's `## Reference calls (verbatim)`
  template section.
- Append the PR entry at the top of `docs/learn/journey.md`.
- Append the PR row to `docs/learn/prs/README.md` index.
- No new glossary or python-notes entries expected (the slice
  introduces no new Python idioms or AI/ML concepts beyond what Slice
  1 already covers).
- Update `specs/roadmap.md`: Phase 4 status from `pending` to
  `partial — public-link passthrough only (Slice 2). OAuth + private
  files deferred to Slice 3.`

## 10. Exit gate

Implementation is complete only when **every** item in
`validation.md` §"Success criteria" has produced concrete evidence
(test output, command results, manual-runbook log) shown to the
user, AND the user has explicitly approved the PR for merge. No
silent claims of "tests pass" without showing the run.
