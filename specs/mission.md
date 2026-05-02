# Mission

> Summary for agents and humans entering the project cold. For full context,
> follow the links to canonical sources.

## What this is

SSM-Transcriber is a local-first audio/video transcription pipeline. The
default path runs entirely on the user's machine via `faster-whisper` and
costs `$0`. Cloud transcription (Deepgram, AssemblyAI, OpenAI Whisper) and
paid LLM features are opt-in only and gated behind a two-gate spend model
that requires both a configured key and an explicit `--budget low|best`
flag, plus cost confirmation before any paid call.

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

- Local-first transcription via `faster-whisper`.
- Multi-source support: local files (Phase 1), YouTube (Phase 2), Google
  Drive (Phase 4).
- Output formats: txt, srt, md, json (Phase 3). Markdown frontmatter is
  general-purpose YAML so output drops into Obsidian, NotebookLM, and
  paste-into-AI workflows without lock-in.
- Opt-in cloud providers behind the two-gate spend model (Phase 5).
- Opt-in LLM post-processing with cheapest-first fallback (Phase 6a).
- Future multi-agent orchestration via LangGraph (Phase 6b).

## Out of scope

- Real-time / streaming transcription.
- Multi-user or hosted/SaaS deployment. This is a single-user local CLI.
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
