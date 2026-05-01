# PR #4 — `docs/learn/` folder + teaching register for AI context files

**Merged:** 2026-04-11  |  **Branch:** `learning/docs-and-context`  |  **Codex review:** yes
**Journey entry:** [`../journey.md#pr-4--teaching-register-and-docslearn`](../journey.md#pr-4--teaching-register-and-docslearn)

## The problem in one paragraph

The project had AI context files (`CLAUDE.md`, `AGENTS.md`, etc.) telling
code-generation tools what to do, but no structured place for the *human*
learning artifacts — the "why did we make this choice?" narratives, the
Python-for-Java-developers notes, the glossary, or the interview prep
stories. Without a separation between AI-facing rules and human-facing
teaching material, the context files would bloat with narrative content that
wastes AI context window tokens, and the learning trail would live in
scattered commit messages nobody re-reads.

## What changed (high level, not file-by-file)

- Created `docs/learn/` as the home for all human-oriented learning artifacts
- Added `python-notes.md` — a living doc of Python idioms with Java analogues,
  each pointing at where the idiom shows up in the repo or plan
- Added `glossary.md` — AI/ML terms that appear in the codebase, with plain
  definitions and repo pointers
- Added `interview-prep.md` — STAR-format stories tied to architectural
  decisions, ready for AI/ML engineering interviews
- Added `journey.md` — running narrative of PRs, newest-first, explaining
  *why* each change mattered
- Added `vibe-coding-notes.md` — meta-observations on working with AI coding
  tools, including context-window cost awareness
- Wired the teaching register conventions into all five AI context files so
  AI tools generate PR descriptions and commit messages in the right style
- Created PR explainer stubs for PRs #1–#3 (retrospective) and this PR

## Why this approach

The key design decision is the **separation between AI context files and
human learning docs**. AI context files (`CLAUDE.md`, etc.) stay short and
rule-focused — they exist to prevent code-generation mistakes. Human material
(narratives, analogies, interview stories) lives in `docs/learn/` where it
doesn't consume AI context window tokens during coding sessions. The AI
context files carry a short pointer to `docs/learn/` for behavioral
instructions (write in teaching register, update living docs), but the bulk
of the human content lives outside the AI's always-loaded context.

The alternative was embedding everything in the AI context files. That would
work for small projects but scales poorly — every token of narrative is a
token of source code the AI can't see.

## New Python idioms introduced

No new Python idioms in code. The `python-notes.md` entries document idioms
already present in the codebase (`from __future__ import annotations`,
`X | Y` union syntax, `Annotated`, `Path`) or specified in `docs/PLAN.md`
(frozen dataclasses, context managers, `Literal` types, `@property`,
module singletons, lazy imports).

## New AI/ML concepts introduced

- Agentic engineering — see [`glossary.md#agentic-engineering`](../glossary.md#agentic-engineering)
- AI context file — see [`glossary.md#ai-context-file`](../glossary.md#ai-context-file)
- Context window — see [`glossary.md#context-window`](../glossary.md#context-window)

## What a reviewer should notice

1. The `python-notes.md` entries for not-yet-implemented code (frozen
   dataclasses, context managers, `Literal`, `@property`) carry a short
   "not yet in code" note instead of a citation. This is deliberate: the
   living-doc rule is *cite merged code only* — `docs/PLAN.md` is a
   specification, not a line of source, so it doesn't count. The pointers
   will be filled in when Phase 1 / Phase 5 files land.
2. The teaching register block in AI context files is deliberately short
   (~3 lines + pointer) to minimize context-window cost. The full conventions
   live in `docs/learn/README.md`.

## Interview angle

- **Story type:** trade-off / learning
- **One-sentence hook:** "I separated AI-facing rules from human-facing
  teaching docs because every token of narrative in an AI context file is a
  token of source code the model can't see."
- **Pointer:** see [`interview-prep.md`](../interview-prep.md) §
  "Context-window cost awareness"
