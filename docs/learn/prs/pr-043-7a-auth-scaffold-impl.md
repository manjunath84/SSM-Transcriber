# PR #43 — Implementation: Phase 7 Slice 7a — Auth Scaffold + S3 Viewer

**Merged:** TBD  |  **Branch:** `feat/7a-auth-scaffold`  |  **Codex review:** TBD
**Spec PR:** Phase 7 mega-spec ([`specs/2026-05-14-hosted-ui/requirements.md`](../../../specs/2026-05-14-hosted-ui/requirements.md)) + per-slice plan ([`specs/2026-05-14-hosted-ui/plan-7a.md`](../../../specs/2026-05-14-hosted-ui/plan-7a.md))
**Journey entry:** [`../journey.md#pr-43--implementation-phase-7-slice-7a-auth-scaffold-s3-viewer`](../journey.md#pr-43--implementation-phase-7-slice-7a-auth-scaffold-s3-viewer)

## The problem in one paragraph

Until this PR, SSM-Transcriber was a single-user local CLI. There was
no way for a second person (the author's wife is the first real
not-technical user) to read a transcript without being handed a
terminal. The constitution explicitly listed "multi-user or
hosted/SaaS deployment" as *out of scope* — so even starting this
work required amending the constitution on purpose. Slice 7a is the
smallest end-to-end vertical slice that proves the hosted surface
works: an *invited* person signs in with Google, sees their existing
transcripts newest-first, opens one to read the markdown, and can
delete it — on a pure-serverless AWS stack that tears down to ≈$0.
No job submission, no cost gate, no Step Functions yet (those are 7b).

## What changed (high level, not file-by-file)

- **Cognito + Google federated sign-in.** A Cognito user pool with
  Google as the identity provider (identity only — *no Drive scope*;
  Drive is a separate opt-in flow deferred to 7c).
- **Invite-gate Lambda.** A Cognito *Pre sign-up* trigger
  (`triggerSource == "PreSignUp_ExternalProvider"`) that rejects any
  Google account whose email has no seeded `#PROFILE` row in DynamoDB.
  Un-invited users never get an account provisioned.
- **S3 + CloudFront SPA.** A Vite + React + TypeScript single-page app
  (sign-in callback, dashboard list with a budget pill, viewer, delete)
  hosted from a private S3 bucket fronted by CloudFront with Origin
  Access Control.
- **DynamoDB single-table.** One table with PK/SK + GSI1/GSI2; in 7a
  only `#PROFILE` items exist (job records and Google tokens are 7b/7c).
- **API Gateway HTTP API + Cognito JWT authorizer**, fronting four
  Lambdas: `list_transcripts`, `get_transcript`, `delete_transcript`,
  `get_me` (profile/budget-pill source).
- **AWS CDK (Python) infra** under `infra/`, self-contained and *not*
  in the core CLI runtime dependency set.
- **Constitution amendments shipped in-PR** (`specs/mission.md`,
  `specs/tech-stack.md`, `docs/PLAN.md` §F1/§F4) plus the CLAUDE.md
  guardrail-line lockstep edit so the two authoritative tool-context
  files don't diverge.

## Why this approach

**IaC = AWS CDK (Python), not SAM (ADR-0).** This slice's infra is
auth- and CDN-heavy: federated Cognito, CloudFront+S3 SPA, an API
Gateway Cognito authorizer. CDK's L2 constructs collapse exactly these
into a few typed lines (`UserPoolIdentityProviderGoogle`,
`HttpUserPoolAuthorizer`, `S3BucketOrigin.with_origin_access_control`).
SAM has no serverless abstraction for a user pool, Google federation,
or CloudFront — it degrades to hand-written raw CloudFormation for
precisely the hard parts. CDK also keeps infra in Python (same
language as the app; its OO construct model maps cleanly onto a Java
background) and ships `aws_cdk.assertions.Template` for the infra unit
tests the spec's F7 lane already calls for. `cdk synth` still emits
CloudFormation for learning; `cdk destroy` is the spec's literal-$0
lever. SAM's genuine edges — teaching raw CFN directly and
`sam local invoke` — don't pay for the YAML tax here because the spec
already covers local testing via `moto`. Decision pinned in the
plan's ADR-0 and spec ADR rows D2/D8/D9; grounded in a Context7 fetch
of `/aws/aws-cdk` and `/aws/serverless-application-model` (2026-05-16).

**The F1 hosting boundary.** F1 says library code stays sync. The
hosted surface is event-driven by nature (Lambda invocations, browser
polling). The resolution is a *named boundary*: everything new lives
under `src/transcriber/hosted/` (an explicitly out-of-the-sync-set
package) and `infra/`, and imports nothing that would add `async def`
to `sources/`, `providers/`, `formatters/`, `destinations/`, `core/`.
The PLAN.md §F1 amendment expands the protected set to add
`destinations/` + `core/`, and — critically — the CLAUDE.md guardrail
line is edited in the *same* PR (commit `929b02d`) so the two
authoritative context files can't drift.

**The invite-gate chicken-and-egg.** The invite-gate Lambda rejects
anyone without a `#PROFILE` row, but the row is keyed by email and the
fixture transcript is keyed by the Cognito `sub` — which doesn't exist
until *after* first sign-in. So the seed script (`infra/seed.py`)
deliberately splits into two subcommands: `invite` (write the
`#PROFILE` row, must run *before* sign-in) and `fixture` (write the
committed transcript, run *after* the user has a `sub`). The ordering
is a real operational contract, not an accident.

## New Python idioms introduced

- AWS Lambda handler signature `def handler(event, _context)` — see
  [`python-notes.md#lambda-handler-signature`](../python-notes.md#lambda-handler-signature)
- `boto3` resource vs. client — see
  [`python-notes.md#boto3-resource-vs-client`](../python-notes.md#boto3-resource-vs-client)
- `argparse` subcommands (subparsers) — see
  [`python-notes.md#argparse-subcommands`](../python-notes.md#argparse-subcommands)

## New AI/ML concepts introduced

- Cognito federated IdP — see [`glossary.md#cognito-federated-idp`](../glossary.md#cognito-federated-idp)
- Single-table design — see [`glossary.md#single-table-design`](../glossary.md#single-table-design)
- Commit marker — see [`glossary.md#commit-marker`](../glossary.md#commit-marker)
- PKCE — see [`glossary.md#pkce`](../glossary.md#pkce)
- CloudFront OAC — see [`glossary.md#cloudfront-oac`](../glossary.md#cloudfront-oac)

## What a reviewer should notice

- **The invite-gate event shape is pinned, not guessed.** Which
  Cognito trigger fires for a *federated* (Google) first sign-in is a
  non-obvious service contract — it's the *Pre sign-up* trigger with
  `triggerSource == "PreSignUp_ExternalProvider"`, not Post
  Confirmation, not a self-service Pre sign-up. The exact trigger name
  *and* event payload were copied verbatim from the AWS Cognito
  Developer Guide into the spec's "Reference calls (verbatim)" section
  before `invite_gate.py` was written — same discipline that caught
  PR #12's wrong-shape bugs.
- **The no-Docker bundling skip is deliberate (commit `33c626f`).**
  CDK's default Lambda asset bundling shells out to Docker. The infra
  is configured to skip Docker bundling so `cdk synth` and the infra
  unit tests run on a plain laptop / CI box with no Docker daemon —
  a testability decision, not a shortcut.
- **The Google client secret lives in Secrets Manager, not an SSM
  SecureString.** D11 makes SSM the cost-sensitive *default* for the
  app's own secrets, but the Cognito Google-IdP construct consumes a
  `SecretValue`, and Secrets Manager is the supported source for that
  here (`infra/stacks/hosted_stack.py:90`). The client *id* is a plain
  SSM string parameter; only the secret is in Secrets Manager.
- **The `manifest.json` commit-marker rule (Codex P2).**
  `transcript.md` + `result.raw.json` are two S3 objects; a partial
  write must never be reader-visible. `manifest.json` is written
  *last*; `s3keys.visible_job_ids` treats a job prefix as existing
  *only if its manifest is present*. The list/get/delete Lambdas all
  go through that one helper.

## Interview angle

- **Story type:** trade-off (technical decision)
- **One-sentence hook:** "I picked AWS CDK over SAM for the hosted
  stack, and the deciding factor wasn't preference — it was that SAM
  has no abstraction for the two hardest things in this slice."
- **Pointer:** `interview-prep.md` → "Tell me about a technical
  decision you made and the trade-offs" (the CDK-vs-SAM STAR story).

## Further reading

- [`specs/2026-05-14-hosted-ui/plan-7a.md`](../../../specs/2026-05-14-hosted-ui/plan-7a.md) — ADR-0 (IaC choice) and the task-by-task plan
- [`specs/2026-05-14-hosted-ui/requirements.md`](../../../specs/2026-05-14-hosted-ui/requirements.md) — the Phase 7 mega-spec, ADR table (D2/D8/D9), and verbatim Cognito reference calls
- [`docs/PLAN.md`](../../PLAN.md) — §F1 / §F4 amendments
