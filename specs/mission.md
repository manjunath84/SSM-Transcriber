# Mission

> Summary for agents and humans entering the project cold. For full context,
> follow the links to canonical sources.

## What this is

SSM-Transcriber is a provider-agnostic audio/video transcription pipeline
where **accuracy is the primary deciding factor**, **cost is the gating
constraint**, and **convenience is a legitimate tiebreaker**. Local
(`faster-whisper`) and hosted (Deepgram, AssemblyAI, OpenAI Whisper)
providers are first-class peers; the user typically picks the most
accurate provider that fits the budget, but may opt for a different
provider for convenience (familiar API, already-configured auth, an
existing workflow already wired through one provider). The default budget
is `free` so casual use costs `$0`, but every paid provider is opt-in
behind a two-gate spend model that requires both a configured key and an
explicit `--budget low|best` flag, plus cost confirmation before any paid
call.

See [`README.md`](../README.md) for the project description, and
[`docs/PLAN.md`](../docs/PLAN.md) §Context for design philosophy.

## Who it's for

1. **The primary author** — a senior Java developer transitioning to AI/ML
   engineering, using this repo as a portfolio piece and learning vehicle.
2. **Interview preparation** — every architectural decision is designed to
   become an interview story.
3. **Developers new to "vibe coding"** — practitioners who want to see how a
   real project sets up AI context files, manages multi-tool consistency,
   and builds verification loops around AI-generated code.
4. **Future contributors and reviewers** — the story, not just the code.
5. **AI coding tools** — read this folder before changing scope; defer to
   `docs/PLAN.md` for technical contracts.

See [`docs/learn/README.md`](../docs/learn/README.md) §"Who this is for" for
the full audience description.

## In scope

- Multi-source ingestion (local files, YouTube, Google Drive) and multiple
  output formats. See [`README.md`](../README.md#roadmap) §Roadmap for the
  phase-by-phase capability list.
- Markdown output uses general-purpose YAML frontmatter so transcripts drop
  into Obsidian, NotebookLM, and paste-into-AI workflows without lock-in.
- Opt-in cloud providers and LLM features behind the two-gate spend model.
- Head-to-head evaluation of providers on **accuracy first, then cost**
  for the same source is a stated future direction. The provider-agnostic
  architecture is built to support it, and those measurements are
  intended to drive subsequent provider and default choices. (MVP ships
  with AssemblyAI as the first hosted provider; the long-term provider
  set is determined by what the evaluations show, with accuracy as the
  primary tiebreaker.)

## In scope (Phase 7, hosted UI)

- Multi-user, hosted/SaaS deployment of the transcription pipeline behind
  a browser UI. The **local CLI remains single-user / local-first** (no
  account, no network dependency, `$0` default); the **hosted UI is the
  multi-user surface** — both guarantees hold simultaneously. Scoped to
  Phase 7; see
  [`specs/2026-05-14-hosted-ui/requirements.md`](2026-05-14-hosted-ui/requirements.md)
  for the full requirements and constitution overrides.

## Out of scope

- Real-time / streaming transcription.
- Long-term storage of raw audio. `RunWorkspace` cleans up temp artifacts.
- Becoming a knowledge management system. Transcripts flow into separate
  downstream tools (Obsidian, NotebookLM, the user's `knowledge-base` repo)
  which own curation. The transcriber's job ends at the markdown file.

## Key concepts

Linked from [`docs/learn/glossary.md`](../docs/learn/glossary.md):
[`provider abstraction`](../docs/learn/glossary.md#provider-abstraction),
[`two-gate spend model`](../docs/learn/glossary.md#two-gate-spend-model),
[`PreparedMedia`](../docs/learn/glossary.md#preparedmedia),
[`RunWorkspace`](../docs/learn/glossary.md#runworkspace),
[`VAD`](../docs/learn/glossary.md#vad-voice-activity-detection).

## Source-of-truth precedence

If `specs/` ever conflicts with `docs/PLAN.md`, `docs/PLAN.md` wins for
technical contracts. If `specs/` ever conflicts with
`docs/learn/README.md`, that file wins for teaching/living-doc rules. This
file is a summary, not a contract.
