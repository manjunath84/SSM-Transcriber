# `docs/ai/` — AI Operator Guide

> This folder is the AI-agnostic workflow layer for SSM-Transcriber. It helps
> tools find the right source docs quickly. It does **not** replace the source
> docs that already own project policy.

## Precedence

1. [`docs/PLAN.md`](../PLAN.md) — detailed technical contracts, roadmap, and
   phase-specific architecture decisions.
2. [`docs/learn/README.md`](../learn/README.md) — living-doc rules,
   teaching-register conventions, PR explainer workflow, and review standards
   for human-facing docs.
3. This folder — repo map, task routing, command inventory, and runbooks for
   multi-step workflows.

If this folder conflicts with `docs/PLAN.md` or `docs/learn/README.md`, the
source docs win. Do not add new detailed technical policy here when it belongs
in one of those two places.

## Repo map

| Path | Why it matters |
|------|----------------|
| `src/transcriber/` | Application code. Phase 0 currently includes only `cli.py` and `config.py`. |
| `tests/` | Smoke tests today; Phase 1 adds fixtures and stubs. |
| `docs/PLAN.md` | Product roadmap and binding F1–F8 contracts. |
| `docs/learn/` | Human-oriented explanations, PR explainers, glossary, and vibe-coding lessons. |
| `docs/ai/runbooks/` | Workflow-heavy playbooks for review, shipping, PR prep, and phase audits. |
| `.claude/commands/` | Claude Code slash commands that dispatch to the runbooks in this folder. |

## Task routing

| If you are... | Read this first | Then read |
|---------------|-----------------|-----------|
| Implementing a feature | `docs/PLAN.md` relevant phase | Tool-specific adapter file (`CLAUDE.md`, `AGENTS.md`, etc.) |
| Reviewing a branch | [`runbooks/review.md`](runbooks/review.md) | `docs/PLAN.md` Phase 1 Foundations; `docs/learn/README.md` if docs changed |
| Preparing a PR | [`runbooks/ship.md`](runbooks/ship.md) | `docs/learn/README.md` and `docs/learn/prs/README.md` |
| Drafting PR narrative/docs | [`runbooks/new-pr.md`](runbooks/new-pr.md) | `docs/learn/README.md` and `docs/learn/prs/README.md` |
| Auditing F1–F8 compliance | [`runbooks/phase-check.md`](runbooks/phase-check.md) | `docs/PLAN.md` Phase 1 Foundations |
| Writing a focused implementation spec | [`specs/README.md`](specs/README.md) | `docs/PLAN.md` phase constraints |

## F1–F8 quick reference

| Contract | One-line reminder | Source |
|----------|-------------------|--------|
| F1 | Keep the core sync through Phase 4; no `async def` on pipeline, source, provider, or formatter methods. | `docs/PLAN.md` → Phase 1 Foundations F1 |
| F2 | Sources return `PreparedMedia`; downstream code does not handle raw URIs. | `docs/PLAN.md` → F2 |
| F3 | Cache keys are versioned composites, never `SHA256(file + quality)`. | `docs/PLAN.md` → F3 |
| F4 | Cloud spend requires both a configured key and an allowed budget. | `docs/PLAN.md` → F4 |
| F5 | One `RunWorkspace` per CLI run; cleanup in `try/finally`; output writes are atomic. | `docs/PLAN.md` → F5 |
| F6 | Surface first-run model downloads; do not let them happen silently. | `docs/PLAN.md` → F6 |
| F7 | Use fixtures/stubs for adapters; gate integration tests explicitly. | `docs/PLAN.md` → F7 |
| F8 | No `print()` in library code, no direct `os.environ`, no secret dumps. | `docs/PLAN.md` → F8 |

## High-signal workflow guardrails

- Keep root tool files compact but self-sufficient: include the few rules an AI
  needs before it can safely start coding, then point here for workflow routing.
- Do not create speculative entries in `docs/learn/python-notes.md` or
  `docs/learn/glossary.md`. Living docs only update when the concept exists and
  can cite a real repo location.
- Do not rewrite git history or force-push without explicit user approval.
- Prefer dedicated workflow commands only for tasks that save real thought or
  typing (`review`, `ship`, `new-pr`, `phase-check`). Generic launchers are
  noise unless they add repo-specific guardrails and output requirements.

## Claude command inventory

| Command | Purpose | Output |
|---------|---------|--------|
| `/review` | Pre-merge review against repo rules and changed files | Findings list + evidence table |
| `/ship` | Ship-readiness check before opening/updating a PR | Readiness checklist + suggested next commands |
| `/new-pr` | Draft explainer/journey content and identify candidate doc updates | PR narrative draft + doc update list |
| `/phase-check` | Audit the current branch against F1–F8 | PASS / FAIL / N/A table with citations |

