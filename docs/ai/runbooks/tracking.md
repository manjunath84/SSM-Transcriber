# Requirement & Work Tracking

Single source of truth for *what's being worked on, what's next, and what's
done*: the GitHub Project board at
<https://github.com/users/manjunath84/projects/3> ("SSM-Transcriber
Roadmap").

The `docs/PLAN.md` roadmap describes the **strategy** (phases, F-contracts,
out-of-scope notes). The Project board tracks the **execution** of that
strategy. `specs/<date>-<slug>/` directories remain the authoritative
record of per-slice requirements; the board issue is a thin pointer +
status container, never a duplicate of the spec.

## Granularity rule (Option A)

**One issue per PLAN.md phase or slice.** Never per PR, never per file or
component.

Why: solo work amplifies issue-management overhead. The PR queue already
shows what's in flight at the commit level; a board entry per PR would
just duplicate that view. The slice is the smallest unit that maps to a
user-visible outcome AND survives across multiple PRs / review rounds.

| Granularity | Verdict | Why |
|---|---|---|
| Phase / slice (one issue) | **Adopted** | Maps to `specs/` 1:1; survives review iterations; ~5–10 issues open at once |
| Per PR | Rejected | Too noisy. Drive upload would have been 5+ issues for one feature |
| Per component / file | Rejected | Issues don't map to user outcomes; degenerates into a todo list |

## Lifecycle

1. **Issue opened** when brainstorm starts. Use the
   `.github/ISSUE_TEMPLATE/slice.yml` template (title format
   `Phase <N> Slice <M> — <slug>`). Status: **Backlog**.
2. **Brainstorm complete** → tick the gate, drop a one-line summary into
   the issue body. Status: **In Spec**.
3. **Spec written** at `specs/<date>-<slug>/requirements.md` → update the
   issue's *Spec* field to the path; tick the gate.
4. **Implementation plan written** (`specs/<date>-<slug>/plan.md` or
   `execution-plan.md`) → tick the gate. Status stays **In Spec** until
   code actually starts.
5. **PR opened** → put `Closes #<issue-number>` in the PR body so merge
   auto-closes the issue. Status: **In Progress**.
6. **Review** (`/ultrareview` if the slice is structural or adds a new
   dependency) → Status: **In Review**. Review-driven follow-up commits
   land on the **same PR**; do **not** open new issues for them.
7. **Merged** → PR closes the issue automatically via the `Closes`
   keyword. Status: **Done**.

## Status columns

The Project's Status field is configured for the 5-column lifecycle:

> **Backlog → In Spec → In Progress → In Review → Done**

(The default GitHub Project Status field ships with *Todo / In Progress
/ Done*. The extra options were added via `gh api graphql` →
`updateProjectV2Field` with the full `singleSelectOptions` list; the
gh CLI doesn't expose this on a regular subcommand. If you ever need to
add another option, the same mutation overwrites the full list, so
pass all five existing options plus the new one — partial updates
delete unmentioned options.)

## Edge cases

- **Slice splits mid-flight.** If during brainstorm a slice grows into
  two (Drive Slice 2 → Slice 3 was a real example: the brainstorm
  decided public-link passthrough should ship before OAuth + private
  files), close the parent issue *only if* nothing landed under it, or
  scope it down to what's shipping now and open a new issue for the
  deferred work. Link the two via the `Spec` field.

- **Cross-cutting fixes** (e.g., the `fix(budget): correct ASSEMBLYAI
  rate` PR #18). No new issue — these are small standalone PRs that
  don't fit any open slice. Use the PR description; the board doesn't
  need to know about them.

- **Documentation-only PRs.** Same as cross-cutting fixes — no issue
  unless the docs work is itself a slice (e.g., `infra: adopt SDD` was
  meaningful enough to be one).

- **Retro issues for already-shipped work.** Created once at board
  setup. Don't open new retros for new shipped work — once the board is
  the source of truth, every shipped slice already passed through it.

## What NOT to track on the board

- File-level todos ("add `sources/youtube.py`, then `tests/...`"). Use
  commit messages / PR descriptions / `specs/<slug>/plan.md` for that.
- Ultrareview findings as separate issues. Findings land as follow-up
  commits on the open PR; the slice issue covers it.
- Backlog ideas that aren't yet phase/slice-shaped. Capture those in
  `docs/PLAN.md` notes; promote to an issue only when concrete.
- Personal dev-environment todos. Not what this board is for.
