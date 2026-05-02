# Plan — AssemblyAI MVP Slice 1

> Numbered task groups. Each group is a coherent chunk that can be
> implemented and reviewed together. Specific function signatures,
> field names, and other implementation details are deliberately *not*
> specified here — the implementer decides those during the build,
> consistent with `specs/tech-stack.md` conventions.

## 1. Dependencies and config

- Add `assemblyai`, `tenacity` to runtime deps; `responses` to dev deps in
  `pyproject.toml`. Run `uv sync` to refresh `uv.lock`.
- Extend `TranscriberSettings` with `keep_temp` (env-overridable), and a
  boundary helper that lets the rest of the codebase ask "is the
  AssemblyAI key configured?" *without* reading `os.environ` outside
  `config.py`. Add a redacted dump of settings so the existing `config`
  CLI command never prints secrets.

## 2. Foundations for this slice (F1, F2, F5, F8 minimal)

Implement the parts of the F1–F8 contracts that this slice actually
depends on, per `requirements.md` §"F1–F8 contracts":

- `PreparedMedia` (F2 minimal).
- A `LocalSource` that returns `PreparedMedia` from a local-file path.
- `RunWorkspace` (F5) — context manager over a temp dir; respects
  `keep_temp`.
- `audio.extract` — ffmpeg-python wrapper that produces a 16 kHz mono WAV
  in the workspace and returns the duration via `ffprobe`.

## 3. Two-gate budget check (F4 minimal)

A budget module that enforces Gate 1 (key configured) AND Gate 2
(`--budget != "free"`), computes the AssemblyAI cost estimate from raw
`ffprobe` duration, and runs the user-facing confirmation flow including
the soft $5 cap warning. Hardcoded around AssemblyAI in this slice;
provider-agnostic generalization is Phase 5 work.

## 4. Provider layer (Phase 5 minimal — AssemblyAI only)

Define a thin `TranscriptionProvider` abstraction with a result type
suitable for what the markdown formatter needs (utterances or paragraphs,
optional speaker labels, language, duration, model identifier, job ID).
Implement the AssemblyAI provider against it: tenacity-wrapped HTTP calls
per the retry policy, polling loop with the configurable wall-clock cap,
and a callback the CLI uses to surface the job ID immediately.

## 5. Markdown formatter (Phase 3 minimal — markdown only)

Implement the formatter that produces output exactly matching the
frontmatter schema and body conventions in `requirements.md`
§"Output frontmatter contract". Honors `--no-speakers` and
`--no-timestamps` flags by stripping the corresponding parts of the body.

## 6. CLI wiring

Replace the existing `transcribe` stub:

- Resolve the source (local file only in Slice 1).
- Open the workspace; extract audio; compute estimated cost.
- Run the budget check (printing job ID happens later, after the provider
  call begins).
- Call the provider; route the job ID through the CLI's `rich` console.
- Render via the markdown formatter; resolve the output filename
  (`{stem}-{YYYY-MM-DD}.md` with suffix-increment on collision); write
  atomically.
- Map exceptions to the documented exit codes (0 / 2 / 3 / 4).
- Wire flags: `--no-speakers`, `--no-timestamps`, `--language`, `--model`,
  `--max-wait`, `--keep-temp`. The existing stub already declares
  `--budget`, `--output`, `-y/--yes`.

## 7. Tests

Unit tests with mocked HTTP (`responses`) cover all the paths in
`validation.md` §"Test cases". A separate `tests/manual/end_to_end.md`
runbook covers the one real AssemblyAI run per release (target cost
≤ $0.01 against a ~10 s WAV fixture).

## 8. Per-PR teaching artifacts

Once implementation lands and before opening the PR:

- Draft `docs/learn/prs/pr-NNN-assemblyai-mvp-slice-1.md` using the repo's
  explainer template.
- Append the PR entry at the top of `docs/learn/journey.md`.
- Append the PR row to `docs/learn/prs/README.md` index.
- Add new glossary entries for any AI/ML or vibe-coding concept this slice
  introduces that isn't already in `glossary.md` (final list determined
  by what the implementation actually uses — likely `tenacity`, possibly
  `AssemblyAI` if useful, possibly `Frontmatter` if not already covered).
- Add new `python-notes.md` entries for any Java→Python idiom this slice
  is the *first* place to introduce in real code (likely `Protocol`,
  `tempfile.mkdtemp` with context manager, `tenacity.retry` decorator,
  `frozen=True` dataclasses with `__post_init__`).
- Update `specs/roadmap.md` Phase 5 status from `pending` to
  `partial — AssemblyAI only` when this slice merges.

## 9. Exit gate

Implementation is complete only when **every** item in `validation.md`
§"Success criteria" has produced concrete evidence (test output, command
results, manual-runbook log) shown to the user, AND the user has
explicitly approved the PR for merge. No silent claims of "tests pass"
without showing the run.
