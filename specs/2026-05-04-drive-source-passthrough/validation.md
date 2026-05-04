# Validation — Drive Source (URL Passthrough)

## Success criteria

Each item below requires **concrete evidence** (command output, file
contents, or manual-runbook log) before this slice can be declared
done. "Tests pass" is not evidence; the test run is.

1. `uv run pytest` passes including all new tests in §Test cases below.
   Evidence: test runner output with the count of new tests.
2. `uv run ruff check src/ tests/` clean.
3. `uv run mypy src/ tests/` clean.
4. The manual integration runbook (`tests/manual/end_to_end.md` —
   Drive scenario) has been executed once against a real Drive file
   the user has already shared as anyone-with-link, and produces a
   markdown file matching the documented frontmatter schema. Evidence:
   the resulting `.md` file (frontmatter visible) and the actual cost
   reported by AssemblyAI dashboard.
5. `uv run ssm-transcriber transcribe "drive://1Zdp9aYV..." --budget free -y`
   exits `2` with the documented Gate 2 message. Evidence: command +
   exit code shown.
6. `uv run ssm-transcriber transcribe "drive://invalid-malformed" -y`
   exits `2` with the documented "could not extract a Drive file ID"
   message. Evidence: command + exit code shown.
7. `git diff main` scope is limited to:
   - `src/transcriber/sources/{base,google_drive,__init__}.py` (or
     `dispatch.py`),
     `src/transcriber/providers/{base,assemblyai}.py`,
     `src/transcriber/formatters/markdown.py`,
     `src/transcriber/cli.py`
   - `tests/unit/` (new + extended files per §Test cases)
   - `tests/manual/end_to_end.md` (Drive scenario added)
   - `docs/learn/` (per-PR teaching artifacts)
   - `specs/2026-05-04-drive-source-passthrough/` (this folder)
   - `specs/roadmap.md` (one status-line update on Phase 4)

   No changes to `pyproject.toml`, `uv.lock`, or `.env.example`.
   Evidence: `git diff main --stat`.

## Test cases

Each case verifies an externally observable behavior, not an internal
implementation detail.

### URL parsing

1. `drive://1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd` → file ID extracted.
2. `https://drive.google.com/file/d/1Zdp.../view` → file ID extracted.
3. `https://drive.google.com/file/d/1Zdp.../view?usp=sharing` → file
   ID extracted (query string ignored).
4. `https://drive.google.com/open?id=1Zdp...` → file ID extracted.
5. `https://drive.google.com/uc?export=download&id=1Zdp...` → file
   ID extracted (round-trips the canonical form back to the same ID).
6. `drive://` (empty) → `ValueError`.
7. `https://drive.google.com/file/d//view` (empty ID segment) →
   `ValueError`.
8. `https://example.com/foo` (non-Drive host) → `resolve_source`
   raises `ValueError` at dispatch with the "URI scheme not supported"
   message; CLI maps to exit 2. (The dispatcher actively rejects
   non-Drive `://` URIs rather than silently treating them as file
   paths — if the user typed `://`, they meant a URL.)

### Source dispatch

9. `resolve_source("drive://...")` → `DriveSource`.
10. `resolve_source("https://drive.google.com/...")` → `DriveSource`.
11. `resolve_source("./video.mp4")` → `LocalSource`.
11a. `resolve_source("https://youtube.com/watch?v=...")` →
     `ValueError` with the "URI scheme not supported" message (until
     YouTubeSource lands in Phase 2; current behavior is reject-not-
     swallow so the failure mode is loud and correct).

### `PreparedMedia` validation

12. Both `local_path` and `remote_url` set → `ValueError` at
    construction.
13. Neither `local_path` nor `remote_url` set → `ValueError`.
14. Only `local_path` set → constructs cleanly (LocalSource path).
15. Only `remote_url` set → constructs cleanly (DriveSource path).

### Provider passthrough (mocked HTTP)

16. `media.remote_url` set: POST `/transcript` body asserted via
    `responses.matchers.json_params_matcher` to include
    `audio_url=<url>`, `speech_models=["universal-3-pro"]`,
    `speaker_labels=true`. **No `/upload` call fires** (the mock for
    `/upload` is registered but `assert_all_requests_are_fired=False`
    holds it; `len([c for c in rsps.calls if "upload" in c.request.url]) == 0`).
17. `media.remote_url` set, AssemblyAI returns 401 →
    `ProviderError`; CLI exit 3. (Existing handling.)
18. `media.remote_url` set, polling returns `error` status with a
    message about not being able to fetch the URL → `ProviderError`
    surfaces the message; CLI exit 3.
19. Local-path tests from Slice 1 (cases 1–9 in the existing
    `validation.md`) still pass — regression coverage that the
    branch on `remote_url` didn't break the upload path.

### Budget gate — Drive variant

20. Both gates pass on Drive source: notify message text contains
    "billing per-minute" or equivalent ("exact cost in dashboard"
    is enough — the implementer picks the exact wording). Soft cap
    line is NOT printed regardless of cost. Confirmation prompt
    fires unless `-y`.
21. Gate 1 fail (no `ASSEMBLYAI_API_KEY`) on Drive source → exit 2
    with the existing Gate 1 message.
22. Gate 2 fail (`--budget free`) on Drive source → exit 2 with the
    existing Gate 2 message.

### CLI

23. `transcribe drive://1Zdp... --title "Session 17" --budget low -y`
    with provider mocked → output written to
    `{output_dir}/Session-17-{date}.md`; frontmatter `title` is
    "Session 17"; frontmatter `source_uri` is `drive://1Zdp...`.
24. Same command without `--title` → output written to
    `{output_dir}/1Zdp...-{date}.md`; frontmatter `title` is the
    file ID.
25. `transcribe "https://drive.google.com/file/d/1Zdp.../view" --title X --budget low -y`
    with provider mocked → identical output to case 23 (URL form
    doesn't matter for the produced artifact).
26. Existing local-file CLI tests still pass — regression.
26a. **`--title` sanitization (security-relevant).** Parametrised
     test: each of `--title "../foo"`, `--title "a/b"`,
     `--title "back\\slash"`, `--title ".hidden"`,
     `--title "ok..bad"` → exit 2 with the documented "unsafe
     filename characters" message. The CLI MUST NOT proceed to
     write a file under those titles. (Without this, the existing
     `atomic.write_text_atomic` will happily create parent dirs and
     write outside `settings.output_dir`.)
26b. `--title "Session 17"` (whitespace) → exits 0; output filename
     contains `Session-17`, frontmatter `title` contains
     `Session 17` (whitespace preserved in the YAML, replaced only
     in the filename).

### Markdown formatter

27. Render against a Drive-shaped `PreparedMedia` (no `local_path`,
    `remote_url` set, `extra={"drive_file_id": "..."}`) → frontmatter
    `source_kind: google_drive`, `source_uri: drive://...`. No
    `file:///` URL appears anywhere in the output.

## Edge cases / what could break

These are not full test cases, but they ARE behavior the
implementation must handle gracefully. Some become tests in §Test
cases above; the rest are documented behavior verified once during
the manual runbook or by inspection.

1. **File shared as anyone-with-link, then sharing revoked between
   command issue and AssemblyAI fetch.** AssemblyAI returns an error
   (HTTP 4xx from `/transcript`, or polling status `error`); existing
   handling surfaces it; exit 3.
2. **Drive file is video-only (no audio stream).** AssemblyAI's
   ingestion or processing will surface this as a polling-status
   error — same path as case 9 above; exit 3.
3. **Drive file >100 MB hits the virus-scan interstitial.**
   AssemblyAI handles the interstitial transparently when fetching
   `audio_url` (verified by the user's reference `curl` in
   `requirements.md` working against a file in this size range).
   Implementation does NOT need its own interstitial logic.
4. **`--title` contains shell-unsafe characters** (`/`, `\`, `\0`,
   `..`, or leading `.`). Reject at the CLI layer with the documented
   "unsafe filename characters" message; exit 2. **This is now a real
   test case (26a above), not just an edge note** — the
   `atomic.write_text_atomic` helper creates parent directories on
   demand, so an unsanitized `--title "../foo"` would write outside
   `settings.output_dir`. Whitespace in `--title` → `-` in the
   filename is fine and intended (26b).
5. **Output filename collision (existing `Session-17-2026-05-04.md`).**
   Existing `atomic.resolve_collision` behaviour applies — writes
   `-2`, `-3`, etc. No new logic needed.
6. **Drive URL with extra query params** (`&authuser=0`, `&hl=en`,
   etc.). Parser ignores everything after the file ID extraction;
   the resulting canonical form has only the required `id=...`
   parameter.
7. **User Ctrl-C during polling.** Workspace cleanup runs (per F5);
   job ID was printed at start; user can recover from AssemblyAI
   dashboard. No new behaviour vs Slice 1.
8. **AssemblyAI changes the `audio_url` parameter name in the future.**
   The `## Reference calls (verbatim)` section in `requirements.md`
   is the dated source-of-truth; PR #13's prevention layer
   (CLAUDE.md guardrails + body-shape mocks) makes this discoverable
   on the next change rather than silent.

## Definition of done

This slice is **done** when, in this order:

1. All §Success criteria items 1–7 have produced concrete evidence
   shown to the user.
2. All §Test cases pass in the test run.
3. The PR explainer, journey entry, prs/README index row have been
   written and committed.
4. `specs/roadmap.md` Phase 4 status has been updated to `partial —
   public-link passthrough only (Slice 2). OAuth + private files
   deferred to Slice 3.`
5. The user has explicitly approved the PR for merge.

None of the above are optional.
