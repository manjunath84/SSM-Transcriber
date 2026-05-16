# Phase 7 — Slice 7e: Guided Local-Transcribe Runbook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a guided, AI-agnostic runbook (plus a thin Claude command and two routing-table rows) so any AI tool can walk a user through transcribing a local file with `uv run ssm-transcriber transcribe` without the user recalling flags.

**Architecture:** Pure documentation slice. One canonical runbook in `docs/ai/runbooks/` (the AI-agnostic surface — every tool adapter already indirects here via `docs/ai/README.md`), one thin Claude-Code command pointer mirroring the existing `.claude/commands/ship.md` pattern, and two new rows in the `docs/ai/README.md` routing/inventory tables. Zero AWS, zero Python, zero test-suite change.

**Tech Stack:** Markdown only. Verification is by inspection: referenced CLI flags must exist in `uv run ssm-transcriber transcribe --help`; intra-repo links must resolve; `git diff --stat` must touch only the three doc paths.

---

## Scope reconciliation (spec vs. repo reality)

The spec (`requirements.md`, slice 7e + D13) says "thin adapters in
`.claude/commands/`, `AGENTS.md`, `.cursorrules`,
`.github/copilot-instructions.md`, `GEMINI.md`." Inspection of those
files shows they do **not** enumerate individual runbooks — each one
already points at `docs/ai/README.md` for "workflow routing and command
inventory." The AI-agnostic adapter is therefore the **`docs/ai/README.md`
routing table**, already consumed by every tool. So 7e edits exactly
three files; the four non-Claude adapter files need **no** change. This
is a deliberate, documented reconciliation of the spec's framing with
the repo's actual indirection pattern — not a scope cut.

**Explicitly out of scope for 7e** (pre-existing, do not fix here):
`AGENTS.md`, `.cursorrules`, `GEMINI.md`,
`.github/copilot-instructions.md` all say "Phase 0 skeleton only,"
which is stale. Correcting current-phase drift in adapter files is
unrelated to 7e and must not be bundled in.

## File structure

- **Create:** `docs/ai/runbooks/transcribe-local.md` — the guided
  runbook. One responsibility: walk an operator/AI through a local-file
  transcribe, honest about cost.
- **Create:** `.claude/commands/transcribe-local.md` — thin Claude Code
  pointer at the runbook (mirrors `.claude/commands/ship.md`).
- **Modify:** `docs/ai/README.md` — add one row to the "Task routing"
  table and one row to the "Claude command inventory" table.

## Cost-accuracy constraint (binding for this slice)

The runbook MUST state current reality: local-file transcription runs
through **paid AssemblyAI** and requires `--budget low` (or `best`);
`--budget free` is rejected because the faster-whisper $0 local
provider is **not yet shipped** (PLAN.md Phase 1 / Phase 2 Slice 2b are
pending). The runbook must not promise a $0 local path. It may note the
$0 path as a future capability with a one-line forward reference.

---

### Task 1: Verify the live CLI flag surface

**Files:** none (read-only verification that the runbook's commands are real)

- [ ] **Step 1: Capture the actual transcribe flag surface**

Run:
```bash
uv run ssm-transcriber transcribe --help
```
Expected: help text listing at minimum these options (the runbook only
uses flags from this set):
`SOURCE` (arg), `-o/--output`, `-l/--language`, `--title`, `--model`
(`universal-3-pro` default | `universal-2`), `--no-speakers`,
`--no-timestamps`, `--budget` (`free|low|best`), `--upload-to-drive`,
`--drive-folder`, `--max-wait`, `--keep-temp`, `-y/--yes`.

- [ ] **Step 2: Confirm free-budget rejection for a local file**

Run:
```bash
uv run ssm-transcriber transcribe ./does-not-exist.wav --budget free; echo "exit=$?"
```
Expected: a non-zero exit with a budget/auth or file error message
(NOT a successful $0 transcription). This confirms the runbook's
"local = paid, needs `--budget low`" framing is accurate. (A
file-not-found exit is also acceptable evidence; the point is no $0
local transcription path exists.)

- [ ] **Step 3: No commit** (verification only — nothing changed)

---

### Task 2: Write the guided runbook

**Files:**
- Create: `docs/ai/runbooks/transcribe-local.md`

- [ ] **Step 1: Write the runbook file**

Create `docs/ai/runbooks/transcribe-local.md` with exactly this content:

```markdown
# Guided Local-File Transcribe Runbook

AI-agnostic guide. Any tool (Claude Code, Codex CLI/UI, Cursor, VS Code
Copilot, Gemini CLI) follows this to walk a user through transcribing a
**local audio/video file** without the user recalling CLI flags.

## What this does

Drives `uv run ssm-transcriber transcribe <LOCAL_FILE> [options]` for a
file already on disk (`LocalSource` → audio extract → AssemblyAI →
markdown). The assistant asks the questions below in plain language,
assembles the command, shows it, and runs it only after the user
confirms.

## Cost reality (state this to the user before running)

Local-file transcription today is a **paid AssemblyAI call** and
requires `--budget low` (or `best`). `--budget free` is rejected for
local files because the $0 local provider (faster-whisper) is not yet
shipped (PLAN.md Phase 2 Slice 2b — the deferred faster-whisper
provider). Do not promise a free local transcription. AssemblyAI bills per audio minute; the CLI
shows an estimate and prompts for confirmation before the paid call
unless `-y` is passed.

## Prerequisites (check, don't assume)

- `ASSEMBLYAI_API_KEY` set in `.env`. If missing, stop and tell the
  user to add it — the run will fail Gate 1 otherwise.
- The file exists and is a readable audio/video file. Resolve the path
  before building the command.
- For optional Drive upload only: `GOOGLE_OAUTH_CLIENT_ID` /
  `GOOGLE_OAUTH_CLIENT_SECRET` set and `auth google-drive` already run
  (see `drive-transcribe-upload.md`). Skip this whole branch if the
  user doesn't want Drive upload.

## Questions to ask the user (one at a time, in order)

1. **Which file?** Absolute or repo-relative path. Verify it exists
   before continuing.
2. **Multiple speakers?** Yes → diarization stays on (default). No /
   single speaker → add `--no-speakers` (cheaper, faster).
3. **Keep `mm:ss` timestamps in the transcript?** Yes → default. No →
   add `--no-timestamps`.
4. **Language?** "Auto-detect" → omit `-l`. Otherwise take a code like
   `en` → add `-l en`.
5. **Speech model?** Default `universal-3-pro` (most accurate). If the
   user wants the cheaper/older model → add `--model universal-2`.
6. **Custom output path?** Default writes
   `output/<file-stem>-<YYYY-MM-DD>.md`. If the user wants a specific
   path → add `-o <path>`.
7. **Also upload the transcript to Google Drive?** No → skip. Yes →
   confirm `auth google-drive` is done, then add `--upload-to-drive`
   and `--drive-folder <FOLDER_ID>` (or rely on
   `TRANSCRIBER_DRIVE_OUTPUT_FOLDER_ID`).

## Assemble and confirm

Build the command from the answers. `--budget low` is always included
for a local file (see Cost reality). Example shape:

```bash
uv run ssm-transcriber transcribe \
  "/path/to/recording.m4a" \
  --budget low \
  --no-speakers \
  -l en
```

Show the assembled command to the user verbatim and state the expected
cost framing ("AssemblyAI bills per audio minute; you'll be prompted to
confirm the estimate before any charge"). Run it only after the user
says go. Do **not** add `-y` unless the user explicitly asks to skip
the cost prompt.

## Expected sequence

1. Cost-confirmation prompt with an estimated `$` figure → user
   confirms.
2. `AssemblyAI job ID: <id>` line.
3. Polling until done (raise `--max-wait 60` if the file is long and
   polling times out at the 30-min default).
4. `✓ Saved to: output/<stem>-<date>.md`.
5. If `--upload-to-drive`: `Uploaded → https://drive.google.com/...`.
6. Exit 0.

## Failure modes

| Symptom | Exit | Meaning | Recovery |
|---------|------|---------|----------|
| Budget error: `--budget free` not allowed for a paid provider | 2 | `--budget free` used for a paid local run | Re-run with `--budget low`. |
| `ASSEMBLYAI_API_KEY` missing message | 2 | Gate 1 not configured | Add the key to `.env`. |
| File not found | 4 | Bad path | Re-resolve the file path with the user. |
| Polling exceeds `--max-wait` | 3 | File longer than the cap | Re-run with `--max-wait 60` (or higher). |
| Upload error after `✓ Saved to:` | 4 | Drive failed; transcript is on disk | `uv run ssm-transcriber upload <path> --drive-folder <FOLDER_ID>` (no AssemblyAI re-charge). |

Exit codes follow the project matrix `{0, 2, 3, 4}` (see
`drive-transcribe-upload.md` for the canonical description).

## Notes

- This runbook never invents flags. Every flag here exists in
  `uv run ssm-transcriber transcribe --help`. If the CLI changes, update
  this runbook in the same PR.
- The $0 local path (faster-whisper) is future work; when PLAN.md
  Phase 2 Slice 2b lands, revise the Cost reality section to offer
  `--budget free` for local files.
```

- [ ] **Step 2: Verify every flag in the runbook exists in the CLI**

Run:
```bash
for f in --budget --no-speakers --no-timestamps -l --model -o --upload-to-drive --drive-folder --max-wait; do
  uv run ssm-transcriber transcribe --help | grep -q -- "$f" && echo "OK  $f" || echo "MISSING  $f"
done
```
Expected: every line prints `OK`. Any `MISSING` is a plan failure —
fix the runbook to match the real flag surface before continuing.

- [ ] **Step 3: Verify the runbook makes no $0-local promise**

Run:
```bash
grep -n -i "free" docs/ai/runbooks/transcribe-local.md
```
Expected: every `free` occurrence is in the *Cost reality* / *Failure
modes* / *Notes* context stating free is **rejected / future**, never a
recommendation to use `--budget free` for a local file. Eyeball the
matches; fix wording if any reads as "use free."

- [ ] **Step 4: Commit**

```bash
git add docs/ai/runbooks/transcribe-local.md
git commit -m "docs(7e): add guided local-file transcribe runbook"
```

---

### Task 3: Add the thin Claude Code command pointer

**Files:**
- Create: `.claude/commands/transcribe-local.md`

- [ ] **Step 1: Confirm the existing thin-pointer pattern**

Run:
```bash
cat .claude/commands/ship.md
```
Expected: a ~4-line file: `Read \`docs/ai/runbooks/ship.md\`.` then
"Follow the runbook exactly." plus a one-line behavioural constraint.
The new file mirrors this shape exactly.

- [ ] **Step 2: Write the command file**

Create `.claude/commands/transcribe-local.md` with exactly this content:

```markdown
Read `docs/ai/runbooks/transcribe-local.md`.

Follow the runbook exactly.
Ask the user the questions one at a time, assemble the command, show it,
and run it only after the user confirms. Never add `-y` unless the user
explicitly asks to skip the cost prompt.
```

- [ ] **Step 3: Verify it matches the pattern and the link resolves**

Run:
```bash
test -f docs/ai/runbooks/transcribe-local.md && echo "link target exists" || echo "BROKEN LINK"
wc -l .claude/commands/transcribe-local.md
```
Expected: `link target exists`; line count is small (≈4–5), confirming
it's a thin pointer, not duplicated content.

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/transcribe-local.md
git commit -m "docs(7e): add /transcribe-local Claude command pointer"
```

---

### Task 4: Wire the runbook into the `docs/ai/README.md` routing tables

**Files:**
- Modify: `docs/ai/README.md`

- [ ] **Step 1: Add the Task-routing row**

In `docs/ai/README.md`, in the "## Task routing" table, immediately
after the existing row that begins
`| Setting up or running Drive transcribe + upload |`, add this new
table row on its own line:

```markdown
| Transcribing a local audio/video file | [`runbooks/transcribe-local.md`](runbooks/transcribe-local.md) | `README.md` § Quick start |
```

- [ ] **Step 2: Add the Claude command inventory row**

In `docs/ai/README.md`, in the "## Claude command inventory" table,
immediately after the `| \`/phase-check\` |` row, add this new row on
its own line:

```markdown
| `/transcribe-local` | Guided local-file transcribe (asks questions, assembles + runs the command) | Confirmed command + transcript path |
```

- [ ] **Step 3: Verify both rows landed and links resolve**

Run:
```bash
grep -n "transcribe-local" docs/ai/README.md
test -f docs/ai/runbooks/transcribe-local.md && echo "routing target exists"
```
Expected: two `grep` hits (one Task-routing row, one command-inventory
row); `routing target exists` printed.

- [ ] **Step 4: Commit**

```bash
git add docs/ai/README.md
git commit -m "docs(7e): route transcribe-local in the AI operator guide"
```

---

### Task 5: End-to-end verification (AI-agnostic claim + scope containment)

**Files:** none (verification only)

- [ ] **Step 1: Cold-read simulation**

Read `docs/ai/runbooks/transcribe-local.md` start to finish as if you
had zero prior context. Confirm: following only the runbook, you can
produce a correct `uv run ssm-transcriber transcribe ...` invocation
for the scenario "transcribe `/tmp/demo.m4a`, single speaker, English,
no Drive." Expected assembled command:
```bash
uv run ssm-transcriber transcribe "/tmp/demo.m4a" --budget low --no-speakers -l en
```
Every flag in it must appear in `uv run ssm-transcriber transcribe --help`.

- [ ] **Step 2: Tool-agnostic routing check**

Run:
```bash
grep -n "docs/ai/README.md" AGENTS.md .cursorrules GEMINI.md .github/copilot-instructions.md
```
Expected: every one of the four adapter files references
`docs/ai/README.md` — confirming all non-Claude tools reach the new
runbook through the routing table with no per-file edit needed (the
documented scope reconciliation).

- [ ] **Step 3: Scope-containment check**

Run:
```bash
git diff --stat origin/main...HEAD -- . ':(exclude)specs/2026-05-14-hosted-ui/'
```
Expected: exactly three files changed —
`docs/ai/runbooks/transcribe-local.md` (new),
`.claude/commands/transcribe-local.md` (new),
`docs/ai/README.md` (modified). No `src/`, no `tests/`, no adapter
files, no `pyproject.toml`. Any other path is a scope breach — revert it.

- [ ] **Step 4: No commit** (verification only)

---

## Self-review checklist (run after the plan is written, before execution)

- **Spec coverage:** Slice 7e requires the canonical runbook + thin
  adapters + verification that any AI tool reaches it. Task 2 (runbook),
  Task 3 (Claude pointer), Task 4 (routing rows), Task 5 (agnostic +
  scope checks) cover this. The spec's "thin adapters in each tool file"
  is reconciled in the Scope-reconciliation section (repo already
  indirects via `docs/ai/README.md`).
- **Placeholder scan:** runbook + command-file content is given
  verbatim; no "TBD"/"add appropriate"/"similar to" anywhere.
- **Path/string consistency:** the runbook path
  `docs/ai/runbooks/transcribe-local.md`, the command path
  `.claude/commands/transcribe-local.md`, and the routing slug
  `/transcribe-local` are identical across Tasks 2–5.
- **Cost accuracy:** Task 1 Step 2 + Task 2 Step 3 enforce the
  "local = paid, `--budget low`, no $0 promise" constraint against the
  live CLI.
