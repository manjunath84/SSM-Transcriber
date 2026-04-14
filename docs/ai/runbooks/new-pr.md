# New PR Narrative Runbook

Use this when starting the PR explainer / teaching-register workflow.

## Read first

1. `docs/learn/README.md`
2. `docs/learn/prs/README.md`

## Required output before writing files

Show the user:

1. Proposed PR title
2. Proposed explainer slug
3. Draft PR explainer content
4. Note whether `docs/learn/journey.md` should wait, or a draft entry if the PR
   number is already known and the user asked for it
5. Candidate living-doc updates

## Rules

- Do not invent or guess a PR number. If the number is unknown, draft the
  title, slug, and explainer content in the response only.
- Do not write a numbered explainer file until the real PR number exists or the
  user explicitly asks for a draft despite that limitation.
- Do not update `docs/learn/journey.md` until the PR number exists, unless the
  user explicitly asks for a draft entry and accepts that it may need follow-up.
- Do not create speculative `python-notes.md` or `glossary.md` entries.
- Only update living docs when the concept exists in the changed code/docs and
  can cite a real repo location.
- Follow the template in `docs/learn/README.md`; do not invent extra sections
  unless the source docs explicitly allow them.
