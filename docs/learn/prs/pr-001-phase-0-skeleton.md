# PR #1 — Phase 0: project skeleton

**Merged:** 2026-04-11  |  **Branch:** `phase/0-skeleton`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-1--phase-0-project-skeleton`](../journey.md#pr-1--phase-0-project-skeleton)

> Retrospective stub. PR #1 predates `docs/learn/`, so this explainer was
> written after the fact from the commit history, the PR description, and
> what shipped on `main`. Everything from PR #3 onward is written fresh
> against the template before the PR opens.

## The problem in one paragraph

The project needed a runnable scaffold. There was no `pyproject.toml`, no
Python package layout, no CLI entry point, no CI, and no AI-tool context
files. Without a scaffold, every later PR would need to invent
project-setup conventions on the fly, different AI coding tools would
produce incompatible code, and there was no green-build baseline to
regress against.

## What changed

- Added `pyproject.toml` pinning Python 3.11+, declaring initial
  dependencies (`faster-whisper`, `yt-dlp`, `typer`, `rich`,
  `pydantic-settings`, `ffmpeg-python`), and wiring the
  `ssm-transcriber` CLI entry point.
- Committed `uv.lock` so `uv sync` is reproducible.
- Added `.python-version` pinning to Python 3.12 to avoid 3.14
  ML-wheel incompatibilities.
- Scaffolded `src/transcriber/` with `cli.py` (typer app with stubbed
  commands), `config.py` (pydantic-settings stub), and `py.typed`
  (marks the package as type-hint-aware).
- Added all five AI tool context files: `CLAUDE.md`, `AGENTS.md`,
  `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md`.
- Added GitHub Actions CI running `ruff check`, `mypy`, and `pytest`
  on every PR and push to `main`.
- Addressed Codex review feedback: committed the lockfile, pinned Python,
  prefixed all internal env vars with `TRANSCRIBER_`, added `py.typed`,
  added config stub.

## Why this approach

Three choices are worth calling out:

1. **`uv`, not `pip` / `poetry` / `pdm`.** `uv` is written in Rust, 10–100×
   faster, and (as of 2024–2025) has become the Python packaging community's
   clear direction. Picking `poetry` would have been defensible a year ago;
   in 2025 it's legacy. Picking `pip` + `requirements.txt` would mean
   managing virtual envs and lockfiles by hand.
2. **Five AI context files instead of one.** Each AI tool reads its own
   conventional file (`CLAUDE.md` for Claude Code, `.cursorrules` for Cursor,
   etc.). Maintaining them all in lockstep is a tax on every PR, but it means
   any AI tool the author opens gives advice that matches the project's
   actual conventions. The alternative — one file that every tool pretends
   to read — leaves the author re-teaching each tool every time they switch.
3. **Stubbed CLI that exits non-zero.** The `transcribe` command prints its
   arguments and exits with code 1. This is deliberate: a stub that silently
   succeeds gets called by shell scripts and fails silently for users.
   Exit-non-zero forces Phase 1 to land a real implementation before anyone
   thinks the project is finished.

## New Python idioms introduced

All seeded in [`../python-notes.md`](../python-notes.md):

- [`from __future__ import annotations`](../python-notes.md#from-__future__-import-annotations)
- [Union syntax `X | Y`](../python-notes.md#union-syntax)
- [`typer` and `Annotated`](../python-notes.md#typer-and-annotated)
- [`pathlib.Path`](../python-notes.md#pathlib-path)
- [Module-level singletons](../python-notes.md#module-level-singletons)
- [Lazy imports](../python-notes.md#lazy-imports)

## New AI/ML concepts introduced

- [`faster-whisper`](../glossary.md#faster-whisper) — default transcription engine

## What a reviewer should notice

- The project-setup choices are high-leverage: `uv`, `pydantic-settings`,
  `typer`, `ruff` + `mypy` in CI. Each of these is a fork in the road you
  rarely revisit, and each one was picked to match 2025 Python conventions.
- The `config` command in `cli.py` currently prints `settings.model_dump()`
  wholesale. Codex flagged this as a P3 risk: safe today because no
  sensitive field is defined, dangerous as soon as one is. F8 (Phase 1
  Foundations) will replace this with `redacted_dump()`.
- `.env.example` uses `TRANSCRIBER_` prefixes for *internal* settings and
  leaves third-party SDK keys unprefixed (because the SDKs themselves read
  the unprefixed names). This is a conscious split, not an oversight.

## Further reading

- [uv docs](https://docs.astral.sh/uv/) — the package manager
- [typer docs](https://typer.tiangolo.com/) — the CLI framework
- [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [ruff](https://docs.astral.sh/ruff/) + [mypy](https://mypy.readthedocs.io/)
- `docs/PLAN.md` Phase 0 — the full Phase 0 spec that this PR implemented
