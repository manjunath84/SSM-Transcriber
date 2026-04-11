# `docs/learn/` — Learning Artifacts

> This folder is where SSM-Transcriber explains itself to a human reader.
> `docs/PLAN.md` is the **technical** source of truth (what, how, contracts).
> This folder is the **teaching** source of truth (why, what it means, how to
> read it if you're new).

## Who this is for

1. **The primary author** — a senior Java developer transitioning to AI/ML
   engineering, new to Python. This is the artifact you come back to in six
   months when you've forgotten why `PreparedMedia` looks like a DTO or what
   the "two-gate spend model" was supposed to protect against.
2. **Interview preparation.** This project is also the author's portfolio
   piece for AI/ML engineering roles. Every architectural decision is
   designed to become an interview story: STAR-format answers for
   behavioral questions, whiteboard-ready system designs, and
   Java-to-Python / AI-ML flashcards. See [`interview-prep.md`](interview-prep.md)
   for the curated index.
3. **Developers new to vibe coding** who want to see how a real project
   sets up AI context files, manages multi-tool consistency, and builds
   verification loops around AI-generated code. See
   [`vibe-coding-notes.md`](vibe-coding-notes.md) for patterns and lessons.
4. **Future contributors and reviewers** who want the story, not just the code.
5. **AI coding tools** (Claude Code, Codex, Gemini CLI, Cursor, Copilot) —
   every context file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`,
   `.github/copilot-instructions.md`) points here and instructs the tool to
   write PR descriptions, commit messages, and plan docs in a teaching
   register by default.

If there's ever a conflict between this folder and `docs/PLAN.md`,
`docs/PLAN.md` wins. Technical contracts take precedence over narrative.

## What's in here

| File | Type | Update cadence | What it's for |
|------|------|----------------|---------------|
| [`journey.md`](journey.md) | Living, reverse-chronological | One entry per merged PR | Running narrative of what was built and *why*, in teaching register. Newest first. |
| [`python-notes.md`](python-notes.md) | Living, topic-organized | Append when a new idiom appears | Java → Python idioms as the code introduces them. Each entry cites the file where the idiom first shows up. |
| [`glossary.md`](glossary.md) | Living, alphabetical | Append when a new concept appears | AI/ML, agentic-engineering, and vibe-coding terms as they land in the code or plan. Plain-language definitions, never more than a paragraph. |
| [`vibe-coding-notes.md`](vibe-coding-notes.md) | Living, topic-organized | Append when a new vibe-coding pattern is learned | Patterns, anti-patterns, and decisions about AI-assisted development. How to set up a repo so AI tools generate correct code on the first try. |
| [`interview-prep.md`](interview-prep.md) | Living, curated | Update when a PR ships a decision worth talking about | Curated index mapping project decisions to interview question types: STAR stories, system design walkthroughs, Python / AI-ML / vibe-coding flashcards, and project elevator pitches (30s / 2min / 5min). |
| [`prs/`](prs/) | One file per merged PR | Written *before* the PR is opened | Per-PR human-readable explainer. Uses the template below. |

**Living doc rule:** only add an entry when a real code change makes that
entry necessary. No speculative content, no preemptive glossary dumps. The
point is that every line in these files is load-bearing for something that
actually happened in the repo.

## How to read this if you're new

1. Start at [`journey.md`](journey.md) — the most recent entry is the most
   recent merged PR. Read top-down until you've caught up.
2. When `journey.md` cites a Python idiom (e.g. `@dataclass(frozen=True)`)
   that you don't recognize, follow the link to [`python-notes.md`](python-notes.md).
3. When it cites an AI/ML term (e.g. VAD, LangGraph), follow the link to
   [`glossary.md`](glossary.md).
4. When it cites a vibe-coding pattern (e.g. context files, plan review),
   follow the link to [`vibe-coding-notes.md`](vibe-coding-notes.md).
5. For the full technical detail of any PR, the matching file in
   [`prs/`](prs/) unpacks the architecture decisions and trade-offs.
6. For the end-to-end phase roadmap and the binding F1–F8 contracts, read
   [`docs/PLAN.md`](../PLAN.md).

## PR explainer template

Every merged PR gets a companion file at `docs/learn/prs/pr-NNN-<slug>.md`
using this template. **Write it before opening the PR** so the PR body can
link to it.

```markdown
# PR #NNN — <Title>

**Merged:** <YYYY-MM-DD>  |  **Branch:** `<branch>`  |  **Codex review:** <yes/no>

## The problem in one paragraph
What was broken, missing, or unclear before this PR — written so a Java
developer new to Python can follow without jargon.

## What changed (high level, not file-by-file)
- bullet
- bullet
- bullet

## Why this approach
The architectural reasoning. Cite alternatives considered and why they
were rejected. This is the section you thank yourself for in six months.

## New Python idioms introduced
- `idiom_name` — see [`python-notes.md#idiom_name`](../python-notes.md#idiom_name)

## New AI/ML concepts introduced
- `term` — see [`glossary.md#term`](../glossary.md#term)

## What a reviewer should notice
Two or three things a sharp reviewer would flag if this PR hadn't been explained.

## Interview angle
If this PR ships a decision worth talking about in an interview, capture it here:
- **Story type:** behavioral (STAR) / system design / trade-off / bug-I-caught / learning
- **One-sentence hook:** the opening line you'd say out loud
- **Pointer:** which section of `interview-prep.md` this lands in
Leave this section out entirely if the PR is mechanical or low-signal — not every PR is interview material.

## Further reading
- Links to specs, blog posts, source repos, or related PRs.
```

## Contribution rules (for humans *and* AI tools)

1. **Write before you open the PR.** The explainer file is part of the PR,
   not an afterthought. Drafting it forces you to articulate the *why*, which
   usually catches sloppy thinking.
2. **Update living docs in the same PR that introduces the concept.** Don't
   leave `python-notes.md` stale — if a PR adds the first use of `@property`,
   that PR also adds the `@property` entry to `python-notes.md`.
3. **Cite real files and real line numbers.** Every entry in `python-notes.md`,
   `glossary.md`, and `interview-prep.md` should point at where the concept
   first appears in this repo. Broken pointers are worse than no pointers.
4. **Teaching register, not textbook register.** Keep each entry short. A
   glossary entry is two sentences. A `python-notes.md` entry is a Java
   analogue plus a 3–6 line Python example plus a pointer. A `journey.md`
   entry is 3–6 paragraphs. A `prs/` file fills the template; it doesn't
   invent new sections.
5. **Consider the interview angle.** When a PR lands a decision worth
   talking about (architectural choice, trade-off, bug caught before
   shipping, boundary design), fill in the "Interview angle" section of
   the PR explainer and — if the story is strong — add or update the
   matching section in [`interview-prep.md`](interview-prep.md). Not every
   PR qualifies; mechanical changes shouldn't pollute the prep file.
6. **When in doubt, omit.** Low-signal entries dilute the rest. The test is:
   "If I'm a Java dev reading this in six months, does this line save me a
   Google search? Or answer a question in an interview?" If neither, drop it.
