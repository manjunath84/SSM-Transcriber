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

The requirements spec is already merged (Phase 7 shipped via PR #38).
Per slice, **two** PRs remain — a plan PR then an implementation PR —
the two-PR SDD lifecycle in `tracking.md` § "Lifecycle". Do **not**
collapse them into one.

**Spec-side (the per-slice plan PR):**

1. **(Optional, fuzziness-gated) GStack `office-hours`** — only if the
   slice has *genuine* unresolved fuzziness (e.g. 7a IaC CDK-vs-SAM,
   IAM scoping, the Codex-flagged Google-token flow). Design-doc is
   **input notes only**, never the repo spec. Skip by default (tokens).
2. **Superpowers `writing-plans`** ingests the already-merged
   requirements (+ office-hours notes if step 1 ran) and authors
   `specs/<date>-<slug>/plan-<slice>.md`. Requirements are **not**
   re-authored in Loop A — that PR already merged. (If a slice has no
   merged requirements yet, that is Loop B.)
3. **GStack `Auto Plan`** over that plan file → CEO/design/eng findings
   + auto-decisions; apply surviving decisions back into the plan.
   *Primary GStack value-add.*
4. **Open the plan PR.** Link keyword **per `tracking.md` + the merged
   spec's "Tracking convention" section** — defer to those, do not
   hardcode it here (a plan/spec-side PR does not ship the slice).
5. **External multi-vendor review on that PR** — `/codex:review` +
   `/pr-review-toolkit:review-pr` (the gate that caught the real
   defects on #38/#39). Fixes land on the same PR.
6. **Merge, then move the board per `tracking.md`** (a spec-side PR's
   keyword does not auto-close — the board move is manual, by design).

**Implementation-side (the implementation PR):**

7. **Superpowers `subagent-driven-development`** → TDD execution on a
   fresh implementation branch.
8. **Open the implementation PR.** Link keyword again **per
   `tracking.md` + the spec's "Tracking convention" section** (a
   feature-shipping PR auto-closes its slice issue and moves the board;
   the mega-spec umbrella #37 stays open until *all* slices land —
   that nuance is the spec's, defer to it).
9. **External multi-vendor review on the implementation PR**, fixes on
   the same PR, merge → board to Done per `tracking.md`.

### Loop B — a genuinely new, fuzzy feature (no requirements spec yet)

Same two-PR discipline plus a requirements step up front:

1. **GStack `office-hours` FIRST** — pressure-test the idea (input
   notes only).
2. **Superpowers `brainstorming`** authors the requirements spec under
   `specs/<date>-<slug>/` per `REQUIREMENTS_TEMPLATE.md`, ingesting the
   notes. (Use `spec-team` only if you first reshape its `/backlog/...`
   output into the repo `specs/` template — rarely worth it vs.
   Superpowers brainstorming.)
3. **Requirements spec PR:** open / review / merge / board-move exactly
   as Loop A steps 4–6 (keyword per `tracking.md`).
4. Then run **Loop A in full per implementable slice**. A feature big
   enough to fan into slices nests: one requirements spec PR up front,
   then a plan-PR + implementation-PR pair *for each slice*.

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
