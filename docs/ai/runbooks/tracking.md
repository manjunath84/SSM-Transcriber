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

## Lifecycle (SDD — separate spec PR + implementation PR)

SSM-Transcriber follows Spec-Driven Development: a slice ships as
**two** PRs (the spec PR and the implementation PR), each with its
own review cycle. The board reflects this:

1. **Issue opened** when brainstorm starts. Use the
   `.github/ISSUE_TEMPLATE/slice.yml` template. Status: **Backlog**.
2. **Brainstorm complete** → tick the gate, drop a summary into the
   issue body. Status: **In Spec**.
3. **Spec written** at `specs/<date>-<slug>/{requirements,plan,validation}.md`
   → update the issue's *Spec* field to the path; tick the gate.
4. **Spec PR opened** with `Refs #<issue>` (not `Closes`) in the body —
   the slice isn't shipped yet, just specified. Status stays **In Spec**.
5. **Spec reviewed externally** (multi-vendor pass per the repo's
   review convention — Gemini / Codex / `/ultrareview`). Tick the gate.
6. **Spec PR merged** → manually move board Status from **In Spec**
   to **In Progress**. (The `Refs` keyword doesn't auto-close, by
   design — the issue stays open until the implementation ships.)
7. **Implementation PR opened** with `Closes #<issue>` in the body
   so the implementation merge auto-closes the issue. Status stays
   **In Progress**.
8. **Review** (`/ultrareview` for structural / new-dependency slices)
   → Status: **In Review**. Review-driven follow-up commits land on
   the **same PR**; do **not** open new issues for them.
9. **Implementation PR merged** → issue auto-closes via the `Closes`
   keyword, board card moves to **Done**. Flip the matching entry in
   `docs/PLAN.md` to reflect the slice as shipped.

## PR linking conventions

| PR type | Keyword | Closes the issue? | Board action |
|---|---|---|---|
| Spec PR (merges `specs/<date>-<slug>/`) | `Refs #N` | **No** — slice isn't shipped yet | Manually move Status to **In Progress** after merge |
| Implementation PR (ships the feature) | `Closes #N` | **Yes** — auto-closes on merge | Card auto-moves to **Done** |
| Cross-cutting fix / docs-only PR | _(no link)_ | n/a | No issue exists for these; they don't belong on the board |

Mixing these up has real consequences: `Closes #N` on a spec PR
would auto-close the issue at the spec-merge point, hiding the
unshipped implementation work from the board entirely.

## Required one-time project setup

The lifecycle above (step 9 in particular) assumes the project's built-in
**"Item closed"** workflow is enabled — that's what moves a card to
**Done** when an implementation PR with `Closes #N` merges. New
GitHub Projects ship with all built-in workflows **disabled**, and
the public GraphQL API does not expose a mutation for editing them
(verified 2026-05: `updateProjectV2Workflow` doesn't exist;
`gh project` has no `workflow` subcommand). The toggle is UI-only.

One-time enable at the
[project's workflows page](https://github.com/users/manjunath84/projects/3/workflows):

| Built-in workflow | Enable? | Why |
|---|---|---|
| **Item closed** | **Yes — Status: Done** | The auto-move that step 9 of the lifecycle assumes. |
| Pull request merged | No | Redundant — impl PRs use `Closes #N`, so the close event already triggers *Item closed*. |
| Item added to project | Optional — Status: Backlog | Saves a manual click on issue creation; aligns with step 1. |
| Auto-close issue | No | Reverse direction (board → issue); not part of this lifecycle. |
| Pull request linked to issue | No | Spec PRs use `Refs` (no auto-close); manually moving to *In Progress* per step 6 is the convention. |

**Symptom check.** If a closed issue's card stays at *In Progress*
after merge, the cause is almost always *Item closed* being off.
Verify with:

```bash
gh api graphql -f query='
{ user(login: "manjunath84") { projectV2(number: 3) {
    workflows(first: 20) { nodes { name enabled } } } } }'
```

As a one-off fix until the workflow is enabled, move the card by API:

```bash
# Look up the project + field + option IDs once and cache them:
gh project field-list 3 --owner manjunath84 --format json \
  | jq '.fields[] | select(.name=="Status").options'

gh project item-edit \
  --project-id PVT_kwHOAMRl3M4BXaap \
  --id <PVTI_…item id> \
  --field-id PVTSSF_lAHOAMRl3M4BXaapzhSnbXM \
  --single-select-option-id c633b6cf  # Done
```

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

## Verification queries

Two things that look intuitive but silently mislead — pin them here so a
future verification script doesn't get them wrong:

### Use GraphQL `projectsV2`, NOT the REST `/projects` endpoint

The classic REST endpoint is for the deprecated Projects (classic) and
returns `404 Not Found` even when a v2 board is linked:

```bash
# WRONG — always 404 for v2 boards
gh api repos/manjunath84/SSM-Transcriber/projects

# RIGHT — returns linked v2 projects
gh api graphql -f query='{ repository(owner: "manjunath84", name: "SSM-Transcriber") { projectsV2(first: 5) { nodes { number title url } } } }'
```

If a verification script reports "no project linked" but the board
clearly exists in the UI, you've hit the REST/v2 trap.

### `gh project item-list --format json` lowercases custom field names

A custom field declared as `"Phase"` (capital P) is rendered in the
JSON output as `"phase"` — lowercased, but otherwise preserved
(spaces stay as spaces). The default fields keep their canonical
names (`status`, `title`). A jq path using the original case
silently returns `null` for every item:

```bash
# WRONG — every item shows null for Phase
gh project item-list 3 --owner manjunath84 --format json | jq '.items[] | .Phase'

# RIGHT — lowercase the field name
gh project item-list 3 --owner manjunath84 --format json | jq '.items[] | .phase'
```

Worse, the wrong query doesn't error — it just returns nulls — so a
verification script that checks "all items have Phase set" will
silently report a fake failure. If field values look unexpectedly
null, check the case first before assuming a real data problem.

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
  `docs/PLAN.md` notes (or a sibling `backlog/` dir — see below);
  promote to an issue only when concrete.
- Personal dev-environment todos. Not what this board is for.

## Optional sibling-folder pattern: `backlog/` for pre-commitment research

SSM-Transcriber does not currently use this pattern, but if research
on uncommitted ideas starts to clutter `docs/PLAN.md`, adopt this
split:

| Where it lives | What it is |
|---|---|
| `specs/<date>-<slug>/` | Committed slice (already on the roadmap + has a board issue) |
| `backlog/<date>-<topic>.md` | Pre-commitment research — one file per topic; **no board issue**, **not** on `docs/PLAN.md` |

**Promotion path** when a backlog item gets committed:

1. File stays in `backlog/` (historical record of the thinking).
2. New entry added to `docs/PLAN.md` under the relevant phase.
3. New issue created on the board using the template.
4. New option added to the Project's main `SINGLE_SELECT` field via
   the GraphQL mutation in the [Status columns](#status-columns)
   section — pass **all existing options plus the new one**, partial
   updates delete unmentioned options.

Document this distinction up front if you adopt the pattern, so
research doesn't accidentally land on the board (or the board doesn't
become a research scratchpad).
