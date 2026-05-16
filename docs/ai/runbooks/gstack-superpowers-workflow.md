# GStack × Superpowers Workflow — Decision Record + Playbook

> **Status:** Adopted 2026-05-16. Revisit triggers at the bottom.
> **Scope:** How AI spec-driven frameworks are combined in this repo.
> Cross-cutting tooling decision — not tied to a phase/slice issue.

## The decision

**Superpowers is the spec author. GStack is the decision/review layer
only. GSD is not installed.**

- **Spec/requirements authoring → Superpowers `brainstorming`.** It
  produces specs natively in this repo's SDD convention
  (`specs/<date>-<slug>/{requirements,plan,validation}.md`,
  `REQUIREMENTS_TEMPLATE.md`, the "Reference calls (verbatim)"
  vendor-API discipline, the F-contract status table, constitution
  precedence).
- **Planning → Superpowers `writing-plans`.** Execution → Superpowers
  `subagent-driven-development` (TDD, per-task spec+quality review).
- **GStack is used only for:** (a) optional adversarial *decision*
  pressure-testing of genuinely fuzzy ideas (`office-hours`), and
  (b) the multi-persona *review* layer (`autoplan` / `plan-*-review`:
  CEO / design / eng).
- **GStack is NOT the spec author here.** Do not route repo specs
  through `spec-team` or take `office-hours` design-docs as the repo
  spec.
- **GSD: not installed, not needed.** On Opus 4.7 (1M context) its
  phase-isolation value is marginal and per-slice spec decomposition
  already delivers it.

## Why (evidence)

- `office-hours` HARD GATE is "your only output is a design document,"
  written to `~/.gstack/projects/{repo}/*-design-*.md` — not the repo
  `specs/` tree.
- `spec-team` is Jira-shaped (`mcp__jira__jira_get`, `KAN-123`),
  Supabase-shaped (`mcp__supabase__list_tables`), and writes to
  `/backlog/{version}/NNN-*.md`. Neither GStack stage emits the repo's
  `REQUIREMENTS_TEMPLATE` sections. Using GStack as author ⇒ constant
  reshaping + drift + loss of the load-bearing defenses that the
  external reviewers (Codex + pr-review-toolkit) repeatedly verified on
  PR #38 / #39.
- Superpowers `brainstorming` already produced the Phase 7 mega-spec
  end-to-end in-convention; both external vendors validated it with
  only fixable nits. Spec authoring is not the bottleneck.
- GStack's genuine edge is *decisions + review*, not authoring.
- Cost: a full GStack pipeline ≈600k tokens/spec; this project is
  cost-sensitive and 7a–7d already have merged requirements.

This runbook is the durable record of the decision; the rationale above
is self-contained and does not depend on any external analysis file.

## The workflow

### Loop A — a slice whose requirements already exist (e.g. Phase 7 7a–7d)

1. **(Optional, fuzziness-gated) GStack `office-hours`** — only if the
   slice has *genuine* unresolved fuzziness (e.g. 7a IaC CDK-vs-SAM,
   IAM scoping, the Codex-flagged Google-token flow). Its design-doc is
   **input notes only**, never the repo spec. Skip by default (tokens).
2. **Superpowers `brainstorming`** authors/updates the repo spec under
   `specs/<date>-<slug>/` per `REQUIREMENTS_TEMPLATE.md` (ingesting the
   office-hours notes if step 1 ran).
3. **Superpowers `writing-plans`** → `specs/<date>-<slug>/plan-<slice>.md`.
4. **GStack `Auto Plan`** over that plan file ("GStack Auto Plan:
   `<plan path>`") → CEO/design/eng findings + auto-decisions; apply
   surviving decisions back into the plan. *Primary GStack value-add.*
5. **External multi-vendor review** — `/codex:review` +
   `/pr-review-toolkit:review-pr` on the spec/plan (the existing repo
   gate that caught the real defects on #38/#39).
6. **Superpowers `subagent-driven-development`** → TDD execution.
7. **`/commit-commands:commit-push-pr`** with `Refs #<slice-issue>`,
   then merge + board move per `tracking.md` and the spec's "Tracking
   convention" section.

### Loop B — a genuinely new, fuzzy feature

`office-hours` FIRST (pressure-test the idea) → Superpowers
`brainstorming` (authors the repo spec, ingesting the notes) → then
Loop A steps 3–7. Use `spec-team` only if you first reshape its
`/backlog/...` output into the repo `specs/` template (rarely worth it
vs. Superpowers brainstorming).

### Handoff mechanism

No skill calls another. Every handoff is **file-path passing**: a
GStack stage emits a markdown artifact → pass that path as input to the
next Superpowers skill. There is nothing to automate; the "combination"
is the artifact chain above.

## When to revisit this decision

- **Execution moves off Opus 4.7 to a smaller-context model** and
  context rot appears mid-slice → re-evaluate installing GSD for
  phase isolation.
- **GStack adds a repo-convention-aware spec emitter** (outputs the
  `REQUIREMENTS_TEMPLATE` sections + Reference-calls-verbatim natively)
  → reconsider GStack-as-author.
- **The user list / product scope grows** such that competitive
  research + role-based scoping (spec-team) materially de-risks a
  feature → reconsider Loop B's spec-team arm.
- **office-hours token cost stops paying back** on the slices where it
  is invoked → drop step 1 of Loop A entirely.
