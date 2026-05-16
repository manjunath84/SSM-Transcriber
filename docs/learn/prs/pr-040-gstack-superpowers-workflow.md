# PR #40 — Decision Record: GStack × Superpowers Workflow

**Merged:** TBD  |  **Branch:** `docs/gstack-superpowers-workflow`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-40--decision-record-gstack--superpowers-workflow`](../journey.md#pr-40--decision-record-gstack--superpowers-workflow)

## The problem in one paragraph

Two AI spec-driven-development frameworks were now installed alongside
this repo's existing Superpowers workflow: **GStack** (`office-hours`
adversarial pressure-testing, `autoplan` CEO/design/eng review,
`spec-team`) and the question of whether to also adopt **GSD**. With
Phase 7 slices 7a–7d still to build, there was no written rule for
which tool authors specs, which only reviews, and how they hand off.
Left undecided, every future slice would re-litigate the question and
risk routing a repo spec through a tool whose output conventions don't
match the repo's load-bearing SDD discipline.

## What changed (high level)

- A new decision-record runbook, `docs/ai/runbooks/gstack-superpowers-workflow.md`,
  recording the call: **Superpowers authors specs; GStack is the
  decision/review layer only; GSD is not installed.**
- A Loop A (slice with merged requirements) / Loop B (new fuzzy
  feature) playbook, plus explicit "when to revisit this decision"
  triggers.
- One routing row added to `docs/ai/README.md`.

## Why this approach

The deciding evidence came from reading the installed skills directly,
not from their marketing. GStack's `office-hours` has a HARD GATE —
"your only output is a design document" written to
`~/.gstack/projects/{repo}/*-design-*.md`, not the repo `specs/` tree.
`spec-team` is Jira-shaped (`mcp__jira__jira_get`, `KAN-123`),
Supabase-shaped, and writes to `/backlog/{version}/NNN-*.md`. Neither
emits the repo's `REQUIREMENTS_TEMPLATE` sections — the
"Reference calls (verbatim)" vendor-API discipline and the F-contract
status table that the external reviewers (Codex + pr-review-toolkit)
*repeatedly leaned on* when they caught real defects on #38/#39. Using
GStack as the author would mean constantly reshaping its output and
losing exactly those defenses. Superpowers `brainstorming` already
produces specs natively in-convention. So GStack's genuine edge —
adversarial decisions and multi-persona review — is used precisely
there, and nowhere else. GSD's phase-isolation value is marginal on
Opus 4.7's 1M context and is explicitly listed as a revisit trigger
if execution moves to a smaller-context model.

## What a reviewer should notice

1. **The two-PR lifecycle.** The first draft of Loop A collapsed
   spec-authoring and implementation into one linear flow ending in a
   single `Refs #` PR. `tracking.md` § "Lifecycle" mandates *two*
   PRs — a spec-side PR (`Refs`, manual board move) and an
   implementation PR (`Closes`, auto-close → Done) — and warns that
   mixing them "has real consequences." Codex caught this; the fix
   makes the boundary temporal and **defers the keyword choice to
   `tracking.md` + the spec's Tracking-convention section** rather
   than hardcoding it (so the runbook can't drift from the source of
   truth).
2. **No out-of-repo pointers.** An early draft cited a personal,
   ephemeral `~/.claude/plans/` file as the "full analysis." A
   checked-in living doc must cite a real repo location (CLAUDE.md
   guardrail; `docs/learn/README.md` rule 3). The rationale is now
   self-contained in the runbook's "Why" section.
3. **Placement tension.** A binding tooling decision lives in the
   `docs/ai/` routing layer, whose own README says not to mint policy.
   Accepted deliberately: the repo has no ADR home, and the user
   explicitly wanted a single revisitable record. The runbook defers
   to (does not contradict) the canonical workflow-tooling table.

## Interview angle

- **Story type:** technical decision / trade-off (and a bug caught in
  external review).
- **One-sentence hook:** "I had two competing AI spec frameworks and
  decided which one authors specs by reading their actual output
  contracts instead of their docs — and an external reviewer caught
  that my workflow had silently collapsed a mandated two-PR lifecycle
  into one."
- **Pointer:** `interview-prep.md` → "Tell me about a technical
  decision you made and the trade-offs."

## Further reading

- [`docs/ai/runbooks/gstack-superpowers-workflow.md`](../../ai/runbooks/gstack-superpowers-workflow.md) — the decision record itself
- [`docs/ai/runbooks/tracking.md`](../../ai/runbooks/tracking.md) — the two-PR SDD lifecycle the rewrite now defers to
- Phase 7 spec: [`specs/2026-05-14-hosted-ui/`](../../../specs/2026-05-14-hosted-ui/)
