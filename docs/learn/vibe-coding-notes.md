# Vibe Coding Notes

> Living doc. Lessons learned about AI-assisted development ("vibe coding")
> as this project is built. Each entry captures a pattern, an anti-pattern,
> or a decision about how to set up a repo so AI tools generate correct code
> on the first try.
>
> If you're new to vibe coding, read top-down — the entries are ordered
> from foundational to advanced. If you're prepping for an interview, see
> [`interview-prep.md`](interview-prep.md) for the actual behavioral stories
> and flashcards.
>
> Add an entry only when a real decision in this repo forces you to.

---

## Table of contents

- [What is vibe coding](#what-is-vibe-coding)
- [AI context files](#ai-context-files)
- [Multi-tool context strategy](#multi-tool-context-strategy)
- [Workflow commands should earn their keep](#workflow-commands-should-earn-their-keep)
- [Context window is currency](#context-window-is-currency)
- ["Don't do" lists beat "do" lists](#dont-do-lists-beat-do-lists)
- [Code examples as anchors](#code-examples-as-anchors)
- [Plan review before code review](#plan-review-before-code-review)
- [Living docs over upfront docs](#living-docs-over-upfront-docs)
- [Teaching register as a forcing function](#teaching-register-as-a-forcing-function)
- [The verification loop](#the-verification-loop)

---

## What is vibe coding

**The practice of building software primarily through natural language
conversation with AI coding tools**, where the developer's main job shifts
from writing code to *directing, reviewing, and verifying* AI-generated
code. The developer sets intent ("transcribe audio from YouTube, local-first,
zero cost by default"), and the AI produces the implementation. The developer
then reviews, tests, and course-corrects.

**Java analogue:** pair programming where your partner is an LLM. You're the
navigator (architecture, constraints, review), the AI is the driver (syntax,
boilerplate, implementation). The ratio flips from traditional pair programming
— in vibe coding the navigator's job is harder because the driver doesn't ask
clarifying questions proactively; it just writes what it thinks you mean.

**Why it matters for this project.** SSM-Transcriber is built with five AI
tools in rotation (Claude Code, Codex, Gemini CLI, Cursor, Copilot). Every
architectural decision — the context files, the teaching register, the plan
review workflow — exists partly to make vibe coding produce correct code
faster. The repo is as much an experiment in *how to direct AI tools* as it
is a transcription pipeline.

**Where it shows up:** every file in this repo was written or reviewed with
AI assistance. The context file strategy is in
[`CLAUDE.md`](../../CLAUDE.md), [`AGENTS.md`](../../AGENTS.md),
[`GEMINI.md`](../../GEMINI.md), [`.cursorrules`](../../.cursorrules), and
[`.github/copilot-instructions.md`](../../.github/copilot-instructions.md).

---

## AI context files

**What they are.** Files at the repo root that AI coding tools read
automatically when you open a session. Each tool has its own convention:
Claude Code reads `CLAUDE.md`, Cursor reads `.cursorrules`, Copilot reads
`.github/copilot-instructions.md`, Codex reads `AGENTS.md`, Gemini CLI
reads `GEMINI.md`. In this repo those root files are compact **adapters**:
they keep the startup guardrails the tool must see immediately, then point to
`docs/ai/README.md` for workflow routing.

**Why they exist.** Without a context file, every AI session starts from
scratch — the tool doesn't know your stack, your conventions, or your
constraints. It will generate `pip install` commands in a `uv` project,
`async def` in a sync codebase, `os.environ` reads in a pydantic-settings
project, and `print()` statements in a `logging`-based codebase. The root
adapter is the cheapest way to prevent these classes of error on the first
turn; the operator guide and runbooks handle the workflow-heavy detail.

**Java analogue:** think of it as a `.editorconfig` + `checkstyle.xml` +
`CONTRIBUTING.md` rolled into one, except it's read by your AI pair
programmer rather than a static analysis tool. Where `checkstyle.xml` says
"max line length 100," a context file says "never use `os.environ` directly,
always use `from transcriber.config import settings`."

**Key lessons from this project:**

1. **Put the most important rules at the top.** AI tools have limited
   context windows; rules near the top get more attention.
2. **Be specific, not aspirational.** "Use pydantic-settings" is useless.
   "Config access: always `from transcriber.config import settings`, never
   `os.environ`" is actionable.
3. **Include the current phase.** AI tools will try to implement features
   from later phases if you don't tell them what exists now.
4. **Link to the authoritative sources.** Root files should point to
   `docs/PLAN.md`, `docs/learn/README.md`, and `docs/ai/README.md` instead
   of trying to inline the entire workflow system.

**Where it shows up:**
[`CLAUDE.md`](../../CLAUDE.md),
[`AGENTS.md`](../../AGENTS.md),
[`GEMINI.md`](../../GEMINI.md),
[`.cursorrules`](../../.cursorrules),
[`.github/copilot-instructions.md`](../../.github/copilot-instructions.md).

---

## Multi-tool context strategy

**The decision.** Maintain five separate root adapters — one per tool — plus
one shared operator guide in `docs/ai/`.

**Why not one file?** Each tool reads only its own conventional filename.
There is no standard that all tools share. A single `AI-INSTRUCTIONS.md`
would be ignored by every tool unless you manually paste it into every
session. The adapters solve first-turn safety; the operator guide and runbooks
solve duplication and workflow drift.

**The cost.** You still maintain five tool files, but they are smaller and more
stable. The source-of-truth rules live elsewhere, so a new workflow or review
rule does not have to be copied into every auto-loaded file.

**How to manage the cost:**
- Keep the root files focused on startup guardrails, not long prose.
- Keep technical policy in `docs/PLAN.md` and living-doc rules in
  `docs/learn/README.md`.
- Use `docs/ai/README.md` and `docs/ai/runbooks/` for workflow routing.
- When you update workflow rules, check adapters and runbooks together.

**Anti-pattern avoided:** some projects put their entire README into the
context file. This wastes most of the context window on information the
AI doesn't need (badges, installation instructions for humans, license
text). Context files should contain only what the AI needs to write
*correct code*.

**Where it shows up:** the five root adapters, `docs/ai/README.md`, and the
runbooks under `docs/ai/runbooks/`.

---

## Workflow commands should earn their keep

**The pattern.** A workflow command is worth adding only when it saves real
thought or packages a repo-specific checklist. Commands that merely restate
"read the docs and do the task" are maintenance overhead disguised as
structure.

**What this looks like here:** this repo keeps only four Claude Code slash
commands:

- `/review` — findings list + evidence table
- `/ship` — ship-readiness checklist with git-safety guardrails
- `/new-pr` — PR narrative workflow without speculative living-doc writes
- `/phase-check` — explicit F1–F8 audit

Generic launchers like `/build` and `/test` were intentionally left out because
they do not buy enough repo-specific value.

**Where it shows up:** `.claude/commands/` and `docs/ai/runbooks/`.

---

## Context window is currency

**The principle.** Every token in the AI's context window is a finite
resource. Tokens spent on low-value information (verbose explanations,
duplicate rules, boilerplate) are tokens *not* available for understanding
your actual code.

**What this looks like in practice:**
- The context files in this project are ~60–80 lines each. They could be
  300 lines. They're not, because the extra 220 lines would push actual
  source code out of the AI's working memory during a coding session.
- Rules are compressed: "Never `os.environ` — use `settings`" instead of
  a paragraph explaining why environment variables are bad.
- The root adapters keep only a short pointer to the learning docs instead of
  a long teaching-register block. Workflow detail lives in `docs/ai/` and
  `docs/learn/`, not in every auto-loaded file.

**Lesson learned:** when adding content to a context file, ask: "Will this
prevent a code-generation mistake?" If the answer is "no, it's for humans"
then it belongs in `docs/learn/`, not in the context file.

**Where it shows up:** the deliberate brevity of the root adapters.
Compare [`CLAUDE.md`](../../CLAUDE.md) (~40 lines of rules) to
[`docs/learn/interview-prep.md`](interview-prep.md) (~480 lines of narrative).
The former is for AI; the latter is for humans. Mixing them would degrade
both.

---

## "Don't do" lists beat "do" lists

**The pattern.** AI tools are more reliably steered by explicit prohibitions
than by positive instructions. "Do not use `async def`" is stronger than
"prefer sync code." The AI will remember the prohibition; it may drift
from the preference.

**Why this works:** LLMs are trained on enormous codebases where `async def`
is common. A positive instruction ("use sync") competes with that prior.
A negative instruction ("do NOT use `async def` through Phase 4") is more
salient because it contradicts the prior and is therefore more memorable
in the attention mechanism.

**This project's "What NOT to do" block** (in
[`.github/copilot-instructions.md`](../../.github/copilot-instructions.md)):
```
- Do not use `print()` — use `rich.console.Console` in the CLI layer
- Do not call cloud APIs without the two-gate check
- Do not add `async def` to pipeline methods through Phase 4
- Do not cache transcripts on `SHA256(file + quality)`
- Do not strip silence from the canonical audio
- Do not log `settings.model_dump()`
```

Each "don't" is paired with a *specific alternative*. "Don't use X" without
"use Y instead" leaves the AI confused.

**Where it shows up:**
[`.github/copilot-instructions.md`](../../.github/copilot-instructions.md)
§ "What NOT to do."

---

## Code examples as anchors

**The pattern.** One 3-line code example in a context file prevents more
AI mistakes than a page of prose rules.

**Why it works:** AI tools are code-generation engines. They pattern-match
on code more reliably than on English. When the context file contains
`from transcriber.config import settings`, the AI's next code generation
will use that exact import. When it says "use the config module," the AI
might generate `import transcriber.config as cfg` or
`from transcriber import config`.

**Examples from this project:**

[`.github/copilot-instructions.md`](../../.github/copilot-instructions.md)
includes:
```python
from transcriber.config import settings
# Use settings.whisper_model_size, settings.transcription_provider, etc.
# Never read os.environ directly.
```

This is the single most effective block in any of the root adapter files.
It tells the AI the exact import path, the attribute naming style, and the
anti-pattern, all in three lines.

**Where it shows up:**
[`.github/copilot-instructions.md`](../../.github/copilot-instructions.md)
§ "Key patterns."

---

## Plan review before code review

**The pattern.** Run your plan through an AI reviewer *before* writing
code. Architectural mistakes caught in a plan document cost minutes to fix;
the same mistakes caught in a working codebase cost days.

**How this played out in PR #3.** The existing `docs/PLAN.md` was sent to
a Codex review. Codex found eight issues — VAD silence-stripping that would
drift subtitle timestamps, a cache key that was under-specified, a cost
model that leaked "key exists" into "key will be used," an async-everywhere
rule that contradicted the sync stack. All were fixed with plan edits before
a single line of Phase 1 code existed.

**The interview-ready version:** "I caught the worst bug of the project in
a plan review, before I'd written a line of code."

**Anti-pattern:** using AI tools only for code generation and doing plan
reviews manually. The AI is better at finding cross-cutting inconsistencies
in a long document (like "Phase 3 depends on unchanged timestamps, but
Phase 1 strips silence") because it holds the entire document in context
at once.

**Where it shows up:** [`journey.md` PR #3](journey.md#pr-3--phase-1-foundations-f1f8),
[`prs/pr-003-phase-1-foundations.md`](prs/pr-003-phase-1-foundations.md).

---

## Living docs over upfront docs

**The pattern.** Don't write documentation speculatively. Write it when a
real code change forces you to.

**Why this matters for vibe coding specifically:** AI tools will happily
generate 500 lines of speculative documentation if you ask. The result is
a glossary full of terms you never use, a python-notes file full of idioms
your code doesn't contain, and an interview-prep with stories about things
you haven't built. None of it is load-bearing, and it rots immediately.

**This project's rule:** "only add an entry when a real code change makes
that entry necessary" (from [`README.md`](README.md)). Every entry in
[`python-notes.md`](python-notes.md) should cite a real file, and every
entry in [`glossary.md`](glossary.md) should cite a real repo location or
source doc that actually exists. The test is: "if I grep the repo for this
concept, do I find a real anchor for it?"

**Where it shows up:** the "Living doc rule" in [`README.md`](README.md).

---

## Teaching register as a forcing function

**The pattern.** Require every PR to explain new concepts in plain language
with a Java analogue. This forces the author (and the AI tools) to
*actually understand* what they're introducing, not just copy-paste it.

**Why it works for learning:** if you can't explain `@dataclass(frozen=True)`
in terms a Java developer would understand ("it's a `record` — immutable
data holder with auto-generated equals/hashCode"), you probably don't
understand it well enough to use it correctly. The teaching register is a
"prove you understand this" gate.

**Why it works for vibe coding:** when the AI writes the PR explainer and
has to produce a Java analogue, it forces a check: does this concept
actually make sense in context? The analogy-writing step catches concepts
that were imported reflexively ("`asyncio` because modern Python") rather
than for a real reason.

**Where it shows up:** the teaching-register pointers in the root adapters and
the contribution rules in [`README.md`](README.md);
[`python-notes.md`](python-notes.md) (every entry has a Java analogue);
[`glossary.md`](glossary.md) (selected entries have Java analogues).

---

## The verification loop

**The pattern.** After every AI-generated change, run the full verification
suite before committing: `uv run pytest && uv run ruff check src/ && uv run mypy src/`.

**Why this matters more in vibe coding than traditional development:**
- AI tools generate code that *looks* right. It often passes a visual spot
  check. But it may have subtle type errors, unused imports, or logic bugs
  that only a linter / type checker / test suite catches.
- The AI's confidence is uninformative. It will present a wrong answer with
  the same tone as a correct one. The test suite is the only reliable
  signal.
- Running the suite after every change — not just at PR time — catches
  problems while the context is still fresh. "Fix the thing you just
  broke" is a much easier prompt than "find the regression introduced
  three sessions ago."

**This project's verification commands:**
```bash
uv run pytest                    # tests pass
uv run ruff check src/           # lint clean
uv run mypy src/                 # types clean
```

**Anti-pattern:** trusting AI-generated code because "it compiled" or
"the tests passed on the first try." Both of those can be true while the
code still violates an architectural contract (like using `os.environ`
instead of `settings`). The linter and type checker catch the class of
errors that unit tests don't.

**Where it shows up:** the "Running the project" section of
[`CLAUDE.md`](../../CLAUDE.md) and the CI workflow in
`.github/workflows/ci.yml`.
