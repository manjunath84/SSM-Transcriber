# `specs/` — Spec-Driven Development

Project constitution and per-feature specs for SSM-Transcriber.

## Constitution

- [`mission.md`](mission.md) — vision, audience, scope.
- [`tech-stack.md`](tech-stack.md) — Layer / Choice / Rationale for engineering decisions.
- [`roadmap.md`](roadmap.md) — sequenced phase plan with status.

## Per-feature specs

Each feature lives in `specs/YYYY-MM-DD-<feature>/`:

- `requirements.md` — goal, non-goals, scenarios, decisions. Use
  [`REQUIREMENTS_TEMPLATE.md`](REQUIREMENTS_TEMPLATE.md) as the starting
  shape; the **Reference calls (verbatim)** section is required for any
  feature that integrates with a third-party API.
- `plan.md` — numbered task groups.
- `validation.md` — success criteria, test cases, edge cases.

## Source-of-truth split

Constitution docs are **lightweight bridges** to canonical sources:
[`README.md`](../README.md), [`docs/PLAN.md`](../docs/PLAN.md),
[`docs/learn/README.md`](../docs/learn/README.md), [`CLAUDE.md`](../CLAUDE.md).

Substantive content stays where it lives. `specs/` adds the per-feature folder
convention and a stable agent-facing front door. If `specs/` ever conflicts
with `docs/PLAN.md`, `docs/PLAN.md` wins for technical contracts; if it
conflicts with `docs/learn/README.md`, that file wins for teaching/living-doc
rules.
