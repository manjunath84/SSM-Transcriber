# Roadmap

> Sequenced phase plan, mirroring [`docs/PLAN.md`](../docs/PLAN.md). Headings
> are verbatim from PLAN.md so this file does not drift; for phase content,
> follow the link. Status reflects merge state on `main` as of the last
> roadmap update.

| Status | Meaning |
|---|---|
| `done` | Phase merged to `main`. |
| `in-progress` | Branch open or work actively underway. |
| `pending` | Defined in PLAN.md but not yet started. |
| `deferred` | Defined but explicitly deprioritized. |

---

## [Phase 0 — Project Skeleton (start here)](../docs/PLAN.md#phase-0--project-skeleton-start-here)

**Status:** done. Project skeleton, CLI stub, CI (ruff / mypy / pytest), lockfile, Python 3.12 pin landed in PR #1.

## [Phase 0.5 — PR #1 Review Fixes (apply on `phase/0-skeleton` before merge)](../docs/PLAN.md#phase-05--pr-1-review-fixes-apply-on-phase0-skeleton-before-merge)

**Status:** done (folded into PR #1 before merge).

## [Phase 1 Foundations (contracts that later phases depend on)](../docs/PLAN.md#phase-1-foundations-contracts-that-later-phases-depend-on)

**Status:** pending. F1–F8 contracts (sync model, `PreparedMedia`, versioned cache key, two-gate spend, `RunWorkspace`, model preflight, fixture strategy, logging) are defined in PLAN.md but not implemented.

## [Phase 1 — MVP: Transcribe a Local File (working end-to-end)](../docs/PLAN.md#phase-1--mvp-transcribe-a-local-file-working-end-to-end)

**Status:** pending. `faster-whisper`-backed local transcription, end-to-end.

## [Phase 2 — Add YouTube Support](../docs/PLAN.md#phase-2--add-youtube-support)

**Status:** pending.

## [Phase 3 — Output Formats + Polish](../docs/PLAN.md#phase-3--output-formats--polish)

**Status:** pending.

## [Phase 4 — Google Drive Source](../docs/PLAN.md#phase-4--google-drive-source)

**Status:** pending.

## [Phase 5 — Cloud Transcription Providers (provider abstraction)](../docs/PLAN.md#phase-5--cloud-transcription-providers-provider-abstraction)

**Status:** pending.

## [Phase 6a — LLM Post-Processing (opt-in, cheapest-first)](../docs/PLAN.md#phase-6a--llm-post-processing-opt-in-cheapest-first)

**Status:** pending.

## [Phase 6b — LangGraph Multi-Agent Foundation](../docs/PLAN.md#phase-6b--langgraph-multi-agent-foundation)

**Status:** pending.

---

## Vertical-slice exception: AssemblyAI MVP Slice 1

**Status:** pending (next feature loop after this constitution PR merges).

The next feature loop ships a vertical slice that touches Phase 1 + Phase 3
+ Phase 5 work concurrently in order to deliver a working tool earlier. The
slice will explicitly mark which F1–F8 contracts it implements in full vs
implements in minimal form vs defers entirely. See the feature spec at
`specs/2026-05-01-assemblyai-mvp-slice-1/` (created in the next feature
loop) for the contract subset and exit criteria.
