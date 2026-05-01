# PR #2 — Phase 0: rename to SSM-Transcriber

**Merged:** 2026-04-11  |  **Branch:** `phase/0-skeleton`  |  **Codex review:** no
**Journey entry:** [`../journey.md#pr-2--project-rename-transcriber--ssm-transcriber`](../journey.md#pr-2--project-rename-transcriber--ssm-transcriber)

> Retrospective stub.

## The problem in one paragraph

The project shipped with a typo in its name (`Transciber`), was renamed to
`Transcriber`, and then renamed again to `SSM-Transcriber` to disambiguate
from the many other tools already using the generic name. Naming is a
branding decision; it gets exponentially more expensive to change after
dependencies and downstream tooling pin themselves to the old name.

## What changed

- GitHub repository renamed to `SSM-Transcriber`.
- `pyproject.toml` `name` field → `ssm-transcriber`.
- CLI entry point → `ssm-transcriber`.
- Python package kept as `transcriber` (the CLI script name and the
  importable package name are allowed to differ — PEP 621 distributes the
  former, the latter is what appears after `import`).
- All five AI context files updated to refer to `SSM-Transcriber` as the
  project and `ssm-transcriber` as the CLI.
- `README.md` updated.

## Why this approach

Keeping the Python *package* named `transcriber` while the distribution
package is `ssm-transcriber` is deliberate: imports like
`from transcriber.config import settings` are shorter and more readable
than `from ssm_transcriber.config import settings` would be. The
PEP 621 / `pyproject.toml` `name` is what users type at the shell
(`uv run ssm-transcriber`); the `[tool.hatch] packages` or
`[project.scripts]` mapping says which Python package the entry point
lives in. They don't have to match.

The alternative — renaming the Python package too — would have meant a
find-and-replace across every `import`, every file under `src/`, every
`from .X import Y`, and every test. Not worth it for zero user-visible
benefit.

## New Python idioms introduced

None — mechanical rename.

## New AI/ML concepts introduced

None.

## What a reviewer should notice

- This PR is the last chance to rename cheaply. Any name that survives
  past Phase 1 (when there are real transcribe calls in test fixtures
  and recorded outputs) would cost days to change.
- The split between "CLI script name" and "Python package name" is worth
  understanding for later PRs, because `ssm-transcriber` is what shows up
  in docs and `transcriber` is what shows up in Python code.

## Further reading

- [PEP 621 — project metadata in pyproject.toml](https://peps.python.org/pep-0621/)
- `docs/PLAN.md` Phase 0.5 — review fixes section for the early naming and
  packaging context
