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
| `src/transcriber/` | Application code. Phase 0 currently has two meaningful modules: `cli.py` and `config.py`. |
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
| Setting up or running Drive transcribe + upload | [`runbooks/drive-transcribe-upload.md`](runbooks/drive-transcribe-upload.md) | `README.md` § Google Drive upload |
| Transcribing a local audio/video file | [`runbooks/transcribe-local.md`](runbooks/transcribe-local.md) | `README.md` § Transcription quick-start |
| Combining GStack + Superpowers for spec/execution | [`runbooks/gstack-superpowers-workflow.md`](runbooks/gstack-superpowers-workflow.md) | `specs/2026-05-14-hosted-ui/` (Phase 7 spec context) |
| Tearing down / restoring the hosted AWS stack | [`runbooks/aws-teardown.md`](runbooks/aws-teardown.md) | `infra/README.md` |

## Claude command inventory

| Command | Purpose | Output |
|---------|---------|--------|
| `/review` | Pre-merge review against repo rules and changed files | Findings list + evidence table |
| `/ship` | Ship-readiness check before opening/updating a PR | Readiness checklist + suggested next commands |
| `/new-pr` | Draft explainer/journey content and identify candidate doc updates | PR narrative draft + doc update list |
| `/phase-check` | Audit the current branch against F1–F8 | PASS / FAIL / N/A table with citations |
| `/transcribe-local` | Guided local-file transcribe (asks questions, assembles + runs the command) | Confirmed command + transcript path |
