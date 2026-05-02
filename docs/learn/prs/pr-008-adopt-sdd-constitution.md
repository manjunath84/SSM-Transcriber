# PR #8 — Adopt SDD: bootstrap project constitution under `specs/`

**Merged:** TBD  |  **Branch:** `sdd/constitution-bootstrap`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-8--adopt-sdd-bootstrap-project-constitution-under-specs`](../journey.md#pr-8--adopt-sdd-bootstrap-project-constitution-under-specs)

## The problem in one paragraph

The repo had effective constitution-equivalent content scattered across
`README.md`, `docs/PLAN.md` (F1–F8 contracts and Phase 0–6 roadmap),
`docs/learn/README.md` (audience), and `CLAUDE.md` (guardrails) — but no
single agent-facing constitution doc. After PR #6 stabilized those sources
of truth, the next risk was the opposite of drift: an AI tool entering
cold could read the project as five separate files with no obvious order.
The author wanted to adopt Spec-Driven Development (SDD) — a workflow
where mission / tech-stack / roadmap come before feature work, and each
feature loop produces a `requirements / plan / validation` triple. The
brownfield trap was real: naively creating a parallel `specs/` layer with
mission/stack/roadmap content would re-create exactly the kind of
duplicate-source-of-truth drift PR #6 just removed.

## What changed (high level, not file-by-file)

- New `specs/` directory with four files (~250 lines total): `README.md`,
  `mission.md`, `tech-stack.md`, `roadmap.md`. All four are
  **lightweight bridges** — they summarize and link to the canonical
  sources rather than restating them.
- `specs/roadmap.md` mirrors `docs/PLAN.md`'s Phase 0–6 headings
  **verbatim** so a rename in PLAN.md is a one-PR fix, not a drift event.
- New `backlog/` directory with a `.gitkeep` for future research notes
  (per the SDD rule "research goes to a backlog, not the roadmap").
- One added line each in `README.md` and `CLAUDE.md` pointing at
  `specs/`. No restructuring of existing content.
- New glossary entry for `Spec-driven development` since the concept now
  has a real home in the repo.

## Why this approach

Three options were on the table: (1) lightweight bridge — small pointer
files; (2) migrate substantive content out of README/PLAN/CLAUDE into
`specs/`; (3) treat `docs/PLAN.md` as the constitution and only create
per-feature folders. The user picked option 1.

Lightweight bridge is the brownfield-correct move. Substantive content
already exists and is stable as of PR #6. Moving it would be a large
refactor that breaks outbound links from `docs/learn/`, `docs/ai/`, and
the journey/explainer cross-references, with no actual content benefit.
Treating PLAN.md as the constitution wholesale would skip the SDD
agent-facing summary surface that future feature loops rely on.

The bridge also keeps the boundary honest: `specs/mission.md` is a
*summary* (small, regenerable, agent-readable in one paste), not a
*contract*. If it ever conflicts with `docs/PLAN.md` on a technical
detail, PLAN.md wins. That precedence is stated explicitly in
`specs/README.md` and `specs/mission.md`.

The roadmap headings being verbatim from PLAN.md is the same idea applied
locally: paraphrasing would create the exact wording-drift risk that
caused PR #6.

## New Python idioms introduced

None — this PR is doc-only.

## New AI/ML concepts introduced

- [`Spec-driven development`](../glossary.md#spec-driven-development)

## What a reviewer should notice

- The PR is intentionally **doc-only**. No `src/` changes; CI gates
  (`ruff` / `mypy` / `pytest`) run only as a parity check.
- `specs/mission.md`, `specs/tech-stack.md`, `specs/roadmap.md` deliberately
  do **not** restate F1–F8 contract bodies. Verify with
  `grep -rn "F1\b\|F2\b" specs/` — the only matches are NAMES inside
  rationale columns, with links back to PLAN.md for bodies.
- The `specs/roadmap.md` "vertical-slice exception" note flags that the
  next feature loop (AssemblyAI MVP Slice 1) will deliberately bend the
  Phase 0→6 ordering to ship a working tool earlier, while explicitly
  marking which F1–F8 contracts the slice implements vs defers. That note
  is the bridge between the constitution and the upcoming feature spec.
- PR #7 (the merge-date backfill that shipped `b798271`) does not have a
  matching `docs/learn/prs/` explainer or `journey.md` entry. That is a
  pre-existing gap — not introduced or addressed by this PR. Worth
  picking up in a small follow-up.

## Interview angle

- **Story type:** workflow design / brownfield adoption.
- **One-sentence hook:** "Adopting Spec-Driven Development on an existing
  repo without re-creating the documentation drift the repo had just
  finished cleaning up."
- **Pointer:** `interview-prep.md` — workflow design / agentic-engineering
  section (entry to be added when interview-prep is next refreshed).

## Further reading

- [`../../specs/README.md`](../../specs/README.md)
- [`../../specs/mission.md`](../../specs/mission.md)
- [`../../specs/tech-stack.md`](../../specs/tech-stack.md)
- [`../../specs/roadmap.md`](../../specs/roadmap.md)
- [`../../docs/PLAN.md`](../../docs/PLAN.md)
- [`pr-006-roadmap-naming-and-hosted-provider-strategy.md`](pr-006-roadmap-naming-and-hosted-provider-strategy.md) — the prior doc-drift cleanup whose lessons shape this PR's bridge approach.
