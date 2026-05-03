# Requirements — &lt;feature name&gt;

> **How to use this template.** Copy to
> `specs/YYYY-MM-DD-<feature>/requirements.md` and fill in. Sections are
> ordered: what we want, what we won't do, how the user experiences it,
> and what binds the implementer. The **Reference calls (verbatim)**
> section is the load-bearing one for any feature that integrates with
> a third-party API — see the rationale block at the bottom of this
> file before deleting it.

## Goal

One paragraph. What ships, who uses it, what it makes possible that
isn't possible today. Avoid implementation language ("call AssemblyAI's
v2 endpoint"); stay at user-flow level ("transcribe a local file via
a paid cloud provider").

## Non-goals

Bullet list. Each entry is a thing a reasonable reader might assume is
in scope but is *deliberately* out. Phrase as the negative + when it
lands instead. Example:

- **Google Drive source.** Slice 2.
- **Real cloud calls in CI.** Manual runbook only.

## Scenarios / user flows

Numbered list of concrete user-visible flows. Include happy path,
common failure modes, and any edge case the implementer might not
intuit. Each scenario should be specific enough to write a test
against. Example:

1. **Happy path.** User runs `<concrete CLI invocation>`. &lt;Concrete
   observable behaviour and exit code.&gt;
2. **&lt;Failure mode&gt;.** &lt;What user did&gt; → &lt;exact error message + exit code&gt;.

## Constraints and decisions

### From the constitution (binding)

Per `specs/tech-stack.md` and `docs/PLAN.md`, list every constitution-
level guardrail that constrains this feature. Quote them; do not
paraphrase. Example: "Sync only. No `async def` in this slice's code
paths."

### Feature-specific decisions

| Decision | Choice | Rationale |
|---|---|---|

One row per decision the brainstorm settled. Rationale should reference
either a constitution doc, a previous PR, or a captured user preference
— never "seemed reasonable."

## Reference calls (verbatim)

> **Required for any feature that integrates with a third-party API.**
> Paste working calls *verbatim*. The implementer copies these into
> tests and code; **never paraphrase from memory or training data**.
> Each call links the docs URL it came from with the retrieval date.
> If no working call exists yet, use ctx7 (or equivalent live-docs
> fetch) and capture the response shape *here* before writing
> implementation code.
>
> Why this is required: vendor APIs change. PR #12 found three
> wrong-shape defects in a single end-to-end run because the
> implementation paraphrased the user's working curl
> (`speech_models: ["universal-3-pro"]`) into stale training-data
> shape (`speech_model: "best"`). The fix to that class of bug is
> structural: pin the working call here, copy from it, never restate.

### `<vendor name>`

**Source:** &lt;docs URL or "user-supplied" if from a working call&gt;
**Retrieval date:** YYYY-MM-DD (so reviewers can tell when this last
matched the live API)

```bash
# Paste the request verbatim (curl, HTTP example, or SDK call).
curl https://api.example.com/v1/endpoint \
  -H "authorization: <KEY>" \
  -H "content-type: application/json" \
  -d '{
    "field_name_exactly_as_api_wants": "value"
  }'
```

```json
// Paste the response verbatim. Shape, field names, and types
// matter — do not summarise or simplify.
{
  "id": "...",
  "status": "queued"
}
```

## Output contracts

Stable schemas for any user-facing artefact (markdown frontmatter,
JSON output, CLI exit codes). Field-by-field, with types. If a field
is optional, say so. Order should be stable for diff-friendliness.

## F-contract status

| Contract | Status | Notes |
|---|---|---|

How this slice implements / partially implements / defers each binding
F-contract from `docs/PLAN.md`. "Deferred" rows must say which phase
picks them up.

## Dependencies added

Runtime: `<pkg>>=<version>`, …
Dev: `<pkg>>=<version>`, …

If any vendor-key env var is required, link the line in `.env.example`
that documents it. If `.env.example` doesn't have a slot, add one in
this PR.

---

## Why this template exists

The `## Reference calls (verbatim)` section is the canonical defence
against "wrong JSON parameter for vendor X" bugs. It pairs with two
CLAUDE.md guardrails:

- HTTP mocks (`responses`) must use `json_params_matcher` to assert
  request body shape, not just URL+method.
- Vendor API calls must reference a verbatim working call here (or a
  fresh ctx7 fetch with retrieval date) — never paraphrase from memory.

Together these three (template section + body-shape matchers + ctx7
fallback) catch wrong-shape bugs at three different points: spec
review, unit-test write-time, and pre-implementation docs research.
PR #13 set them up; PR #12's incident motivated them.
