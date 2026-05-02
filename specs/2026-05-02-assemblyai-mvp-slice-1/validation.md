# Validation — AssemblyAI MVP Slice 1

## Success criteria

Each item below requires **concrete evidence** (command output, file
contents, or manual-runbook log) before this slice can be declared done.
"Tests pass" is not evidence; the test run is.

1. `uv run pytest` passes including all new tests in §Test cases below.
   Evidence: test runner output with the count of new tests.
2. `uv run ruff check src/ tests/` clean.
3. `uv run mypy src/ tests/` clean.
4. The manual integration runbook (`tests/manual/end_to_end.md`) has been
   executed once against the real AssemblyAI API and produces a markdown
   file matching the documented frontmatter schema. Evidence: the
   resulting `.md` file (frontmatter visible) and the actual cost
   reported by AssemblyAI (≤ $0.01 against the documented fixture).
5. `uv run ssm-transcriber transcribe <fixture>.wav --budget free -y`
   exits `2` with the documented "AssemblyAI is paid" message. Evidence:
   command + exit-code shown.
6. `uv run ssm-transcriber transcribe nonexistent.mp3 --budget low -y`
   exits `4` with a clear "file not found" message.
7. `git diff main` scope is limited to:
   - `src/transcriber/{sources,core,providers,formatters}/`,
     `src/transcriber/cli.py`, `src/transcriber/config.py`
   - `tests/unit/`, `tests/manual/`, `tests/fixtures/`
   - `pyproject.toml` and `uv.lock` (deps only)
   - `docs/learn/` (per-PR teaching artifacts)
   - `specs/2026-05-02-assemblyai-mvp-slice-1/` (this folder)
   - `specs/roadmap.md` (one status-line update on Phase 5)
   No other files. Evidence: `git diff main --stat`.

## Test cases

Each case verifies an externally observable behavior, not an internal
implementation detail.

### Provider (mocked HTTP)

1. Upload + create-transcript + poll: happy path returns a populated
   transcript result.
2. First HTTP call returns 429; second returns 200 — succeeds via
   tenacity.
3. Three consecutive 429s — fails after retry exhaustion (no fourth
   attempt).
4. 401 from auth — fails immediately, no retry.
5. 422 (or any other 4xx) — fails immediately, no retry.
6. Polling returns `status="completed"` after N polls — succeeds; assert
   the poll count.
7. Polling returns `status="error"` with an error message — surfaces the
   error message to the caller.
8. Polling exceeds the wall-clock cap (mocked time) — fails with the job
   ID still recoverable from the error.
9. The job-ID callback fires exactly once, immediately after the
   create-transcript call returns.

### Budget gate

10. No `ASSEMBLYAI_API_KEY` configured → Gate 1 fails with a clear
    error mentioning the env var.
11. `--budget free` (default) → Gate 2 fails with the documented
    "AssemblyAI is paid" error, even when the key is present.
12. Both gates pass and `--yes` not set → confirmation prompt called once.
13. Both gates pass and `--yes` set → confirmation prompt NOT called.
14. Estimated cost > $5 → soft-cap warning printed; confirmation flow
    otherwise unchanged.

### Workspace

15. Happy path: temp dir created, child paths returned correctly,
    cleanup runs on `__exit__`.
16. `keep_temp=True` → temp dir preserved after `__exit__`.
17. Cleanup robust to a `KeyboardInterrupt` raised during the body.

### Atomic write

18. Successful write places the final file at the target path; no
    `.tmp` file remains.
19. If the `.tmp` write fails midway, no partial file appears at the
    target path; any pre-existing file at the target path is intact.

### Formatter

20. Golden file: render against a fixed transcript-result fixture and
    assert byte-for-byte equality with `tests/fixtures/golden/sample.md`.
21. `--no-speakers` strips speaker prefixes from the body.
22. `--no-timestamps` strips `[mm:ss]` prefixes from the body.

### CLI

23. Exit-code matrix with all subsystems mocked: `0` happy and
    user-declined; `2` budget/config; `3` provider; `4` local file or
    ffmpeg error.
24. Output filename collision: existing `foo-2026-05-02.md` causes the
    next run to write `foo-2026-05-02-2.md`. A third run writes `-3`.

## Edge cases / what could break

These are not full test cases, but they ARE behavior the implementation
must handle gracefully. Some become tests in §Test cases above; the rest
are documented behavior verified once during the manual runbook or by
inspection.

1. **`ffmpeg` not installed on the host.** ffmpeg-python raises a
   confusing `FileNotFoundError`; the implementation must catch it and
   surface a clear "install ffmpeg" message; exit `4`.
2. **Source has no audio stream** (e.g. silent video, or text file
   renamed `.mp4`). Either ffmpeg fails extraction or AssemblyAI returns
   a 0-duration error. Either way, surface clearly.
3. **Very long source** (>2 hours). Cost estimate may exceed the soft
   cap; the user should see the louder warning before paying.
4. **AssemblyAI returns no `utterances` field even with diarization on**
   (rare for very short audio). The formatter must fall back to
   paragraphs or words rather than crashing.
5. **Output dir does not exist.** The CLI creates it (`mkdir parents=True
   exist_ok=True`) before the atomic write.
6. **Output dir not writable.** Atomic write fails; surface as exit `4`
   with the OS error message.
7. **Disk full during `.tmp` write.** Caught; partial `.tmp` removed;
   any pre-existing target file intact; exit `4`.
8. **User Ctrl-C during polling.** Workspace cleanup runs (unless
   `--keep-temp`); job ID was already printed so the user can manually
   fetch the result from the AssemblyAI dashboard.
9. **Concurrent runs against the same source on the same day.** Race
   window between collision check and atomic write is small but real.
   Documented as "single-user CLI; not concurrency-safe."
10. **AssemblyAI rate-limited transient 429.** Retried per tenacity
    policy; if still failing after retries, exit `3` with a retry hint.
11. **Filenames with special characters** (spaces, parens, unicode). The
    `Path` machinery must round-trip them safely; the slug-stem extraction
    used for the output filename must not mangle them silently.
12. **`.env` accidentally committed.** Not directly this slice's
    responsibility, but the existing `.gitignore` covers it. Verify by
    inspection during the manual runbook.

## Definition of done

This slice is **done** when, in this order:

1. All §Success criteria items 1–7 have produced concrete evidence shown
   to the user.
2. All §Test cases pass in the test run.
3. The PR explainer, journey entry, prs/README index row, and any new
   glossary / python-notes entries have been written and committed.
4. `specs/roadmap.md` Phase 5 status has been updated to `partial —
   AssemblyAI only`.
5. The user has explicitly approved the PR for merge.

None of the above are optional.
