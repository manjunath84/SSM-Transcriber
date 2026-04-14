# PR #5 — AI operator guide + workflow commands

**Merged:** TBD  |  **Branch:** `infra/agent-skills-commands`  |  **Codex review:** yes

**Journey entry:** [`../journey.md#pr-5--ai-operator-guide--workflow-commands`](../journey.md#pr-5--ai-operator-guide--workflow-commands)

## The problem in one paragraph

The repo started with five AI tool files at the root, each carrying the same
core rules in slightly different formats. That worked for a small Phase 0
project, but it was already turning into maintenance churn: every workflow or
contract tweak wanted to touch `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`,
`.cursorrules`, `.github/copilot-instructions.md`, and sometimes `docs/learn/`
too. The goal of this PR is to reduce that drift risk without swinging to the
other extreme of "one giant AI doc that every tool has to rediscover manually."

## What changed (high level, not file-by-file)

- Added `docs/ai/README.md` as an AI-agnostic operator guide
- Added `docs/ai/runbooks/` for review, ship, PR prep, and F1–F8 audits
- Added a small `.claude/commands/` set for the workflow-heavy tasks only
- Trimmed the five root tool files into compact adapters that keep startup
  guardrails inline and point to the canonical docs for detail
- Updated project docs so `docs/PLAN.md`, `docs/learn/README.md`, and
  `docs/ai/README.md` describe the same workflow model

## Why this approach

The key design choice is **layered context, not one more source of truth**.
`docs/PLAN.md` still owns detailed technical contracts. `docs/learn/README.md`
still owns teaching-register and living-doc rules. `docs/ai/README.md` is the
operator guide that tells an AI which source doc to consult for which task. It
is intentionally a routing layer, not a new policy owner.

The second design choice is **commands should earn their keep**. Generic
commands like `/build` or `/test` look tidy on paper but don’t buy much over a
normal prompt. This PR keeps only the commands that package a real workflow and
required output artifact: `/review`, `/ship`, `/new-pr`, and `/phase-check`.

Finally, the PR avoids two workflow footguns that showed up in earlier review:
it does not create speculative living-doc entries, and it does not make squash
or force-push the default behavior of a ship command.

## New Python idioms introduced

- None in code. This PR is workflow/docs-only.

## New AI/ML concepts introduced

- [`AI context file`](../glossary.md#ai-context-file)
- [`runbook`](../glossary.md#runbook)
- [`slash command`](../glossary.md#slash-command)

## What a reviewer should notice

- `docs/ai/README.md` is a routing/index layer, not a second copy of F1–F8
- The root tool files stay compact, but they are not empty pointers; they still
  carry the few startup guardrails an agent needs immediately
- `/new-pr` and `/ship` explicitly avoid the speculative-doc and auto-squash
  pitfalls flagged in the first PR #5 design review

## Interview angle

- **Story type:** system design / trade-off
- **One-sentence hook:** "I split AI workflow guidance into source docs,
  tool-specific adapters, and runbooks so multiple coding assistants could stay
  consistent without copying the full rulebook into every prompt."
- **Pointer:** [`../interview-prep.md#how-do-you-use-ai-tools-in-your-development-workflow`](../interview-prep.md#how-do-you-use-ai-tools-in-your-development-workflow)

## Further reading

- [`docs/ai/README.md`](../../ai/README.md)
- [`docs/ai/runbooks/review.md`](../../ai/runbooks/review.md)
- [`docs/learn/vibe-coding-notes.md#workflow-commands-should-earn-their-keep`](../vibe-coding-notes.md#workflow-commands-should-earn-their-keep)
