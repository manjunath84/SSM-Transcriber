# Requirements — Phase 7: Hosted multi-user web UI

> Brainstorm output (requirements doc). `plan.md` is produced by
> `/superpowers:write-plan`; `validation.md` lands at implementation time.
> Brainstormed 2026-05-14 with the visual-companion. This spec is a
> **mega-spec** by explicit user choice — it covers the whole Phase 7
> surface but is internally divided into independently-implementable
> slices (7a–7e) so `write-plan` can target one slice at a time.

## Goal

Add a hosted, multi-user web application on top of the existing
SSM-Transcriber pipeline. An invited user (initially the primary author
and his wife) signs in with Google, submits a transcribe job from a
YouTube URL, a Google Drive link, or a local file upload, approves the
estimated cost, watches live status, and reads the resulting markdown
in-app — with an optional copy delivered to their Google Drive. The
existing local CLI is unchanged and remains the offline, $0, local-first
surface; the hosted UI is a separate surface that coexists with it. A
guided, AI-agnostic local-transcribe runbook (slice 7e) removes the need
to memorise CLI flags for local runs. The deployment target is AWS,
pure-serverless, scaling to ≈$0 at idle by construction.

## Non-goals

- **faster-whisper / local ASR in the cloud.** Never in the hosted UI.
  The local CLI keeps the faster-whisper path when PLAN.md Phase 2b
  lands. Hosted is AssemblyAI-only.
- **Unified local↔hosted visibility.** A laptop CLI run does NOT appear
  in the web UI. Google Drive is the bridge (`--upload-to-drive`,
  already shipped). Considered ("Reading 2") and explicitly rejected to
  preserve the constitution's local-first $0 default and avoid dual CLI
  code paths.
- **Sharing transcripts between users.** Deferred. Drive sharing is the
  v1 workaround. Lands post-7d if a concrete need arrives.
- **Inline transcript editing / correction.** Deferred post-7d.
- **Cross-transcript search.** Deferred. v1 is list + open only.
- **Public self-service sign-up.** Invite-only for v1. The architecture
  does not preclude it later (Cognito self-service is a config change).
- **WebSocket / real-time push.** Polling + SES email covers every real
  case for minutes-to-tens-of-minutes jobs at $0 idle. Revisit never
  unless sub-second status matters.
- **Real-time collaborative editing.** Not planned.
- **Mobile-native apps.** Responsive web only.

## Scenarios / user flows

1. **Guided local transcribe (slice 7e, no AWS).** From any AI tool
   (Claude Code, Codex CLI/UI, Cursor, VS Code Copilot, Gemini CLI),
   the user invokes the guided runbook; it asks source / Drive-upload /
   speakers / quality in plain language and runs the correct
   `uv run ssm-transcriber transcribe …`. No flags memorised. **$0 AWS**
   (7e adds zero infra cost; the transcription itself is the existing
   paid AssemblyAI call — the runbook states this explicitly).
2. **Sign in (7a).** User opens the web app → "Sign in with Google" →
   Cognito Hosted UI with Google as the identity provider
   (identity/authentication only — **no Drive scope here**) → lands on
   the dashboard. An un-invited Google account is rejected with a clear
   "not invited" message (exit: no account provisioned). Drive access is
   a **separate** opt-in consent (see Scenario 2b below), never
   bundled into sign-in.
2b. **Enable Drive upload (7c, opt-in).** When the user first turns on
   Drive upload, the app runs a **separate Google OAuth
   authorization-code consent** (scope `drive.file`, offline access).
   The refresh token is exchanged + stored KMS-encrypted server-side.
   Declining leaves the app fully usable without Drive.
3. **View existing transcript (7a).** Dashboard lists the user's
   transcripts newest-first with a budget pill. Clicking one renders the
   markdown + YAML frontmatter with a metadata sidebar and
   download / open-in-Drive / delete actions.
4. **Submit a YouTube job, captions available (7b).** User pastes a
   YouTube URL, submits. Probe finds captions → $0 path → no cost gate →
   transcript in S3 + viewer within seconds. Frontmatter
   `source_kind: youtube_captions`.
5. **Submit a YouTube job, no captions (7b).** Probe finds no captions →
   `reserve-budget` holds the estimate → cost-gate modal shows duration,
   rate, estimated cost, remaining budget, and post-job balance → user
   approves → audio downloaded → AssemblyAI → settle → markdown in S3.
   Frontmatter `source_kind: youtube_audio`, `provider: assemblyai`.
6. **Submit a Drive URL (7b).** Public Drive link → HEAD probe
   (`Content-Length`). Drive bytes don't map cleanly to billable audio
   minutes, so the cost gate can't show an exact figure — **but Gate 3
   must still bound spend (Codex P1 fix)**: the job reserves a
   **conservative ceiling** before approval, derived from
   `Content-Length ÷ a configured minimum-audio-bitrate` →
   max-plausible-minutes × rate, and hard-capped by a configurable
   `max_drive_reservation_usd`. Approval is **blocked** if that ceiling
   exceeds `remaining_budget_usd` (same Gate-3 path as Scenario 9).
   Cost gate shows "estimate uncertain; up to ~$X reserved against your
   budget, actual billed per audio minute and reconciled on settle" →
   approve → AssemblyAI `audio_url` passthrough (no Lambda download) →
   settle to actual, refund (ceiling − actual).
7. **Upload a local file (7c).** User picks "Upload file" → browser
   gets a presigned S3 PUT (≤500MB, audio/* or video/*) → uploads →
   probe → cost gate → AssemblyAI ingests from a presigned S3 GET →
   markdown in S3; optional Drive copy if enabled; SES "ready" email.
8. **Cost gate timeout (7b).** User submits, leaves. After 24h with no
   approval, the Step Functions heartbeat fires → job `cancelled` →
   full budget refund → "expired" email.
9. **Insufficient budget (7b/7d, Gate 3).** Estimate exceeds the user's
   `remaining_budget_usd` → `reserve-budget` conditional write fails →
   job `failed` with "estimated $X exceeds your remaining $Y this month;
   ask the admin to raise your cap" → no AssemblyAI call.
10. **Admin invites a user (7d).** Admin (the primary author) opens
    `/admin`, invites an email (Cognito admin-create), sets
    `monthly_budget_usd`. The invitee can now sign in; their jobs
    consume against the cap and are refused past it.
11. **Job fails mid-AssemblyAI (7b).** A Lambda crash of unknown billing
    impact → job `failed`, `settlement_state=failed`, reservation NOT
    refunded (conservative), CloudWatch alarm → admin reconciles
    manually via `/admin`.
12. **AWS dormancy (cost control).** User runs the teardown runbook;
    IaC `destroy` takes the hosted stack to literal $0. Later, `deploy`
    brings it back. The local CLI was unaffected throughout.

## Constraints and decisions

### From the constitution (binding) — and the amendments this spec ships

`specs/mission.md` currently lists **"Multi-user or hosted/SaaS
deployment. This is a single-user local CLI."** as *out of scope*. This
spec **deliberately overrides that.** The implementation PR(s) ship the
following constitution edits — they are part of Phase 7, not a separate
PR:

| File | Edit |
|---|---|
| `specs/mission.md` | Move "Multi-user or hosted/SaaS deployment" from *Out of scope* to *In scope (Phase 7, hosted UI)* with a back-link to this spec. The local CLI remains single-user/local-first; the hosted UI is the multi-user surface. |
| `specs/tech-stack.md` | Add an AWS-deployment section: Lambda, Step Functions, DynamoDB, S3, Cognito (+Google IdP), API Gateway HTTP API, CloudFront, SES, EventBridge, SSM Parameter Store / Secrets Manager. Rationale per row. |
| `docs/PLAN.md` §F1 | Extend verbatim: *"Library code (`sources/`, `providers/`, `formatters/`, `destinations/`, `core/`) stays sync. Orchestration MAY be event-driven (Step Functions, browser polling) at the hosting boundary only. No `async def` in library code."* **Note: real F1 + CLAUDE.md's guardrail currently name only "pipeline, source, provider, or formatter". This amendment expands that set (adds `destinations/`, `core/`). The implementing PR MUST update the `CLAUDE.md` "Guardrails to keep inline" sync line in the same PR, or the two authoritative tool-context files diverge.** |
| `docs/PLAN.md` §F4 | Extend verbatim: *"The hosted UI adds Gate 3 (per-user monthly spend cap) on top of Gate 1 (configured) and Gate 2 (budget tier). The CLI remains two-gate."* |

Other binding constraints carried unchanged:

- **No `print()` in library code; no secrets in logs or user-facing
  output.** CloudWatch structured logs follow the same rule;
  `redacted_dump()` discipline extends to any diagnostic Lambda output.
- **Atomic output writes (Codex P2 fix).** A single S3 PUT is atomic,
  but `transcript.md` + `result.raw.json` are **two** objects. Both are
  written first, then a small `manifest.json` is written **last** as
  the commit marker. The list/get Lambdas and the viewer treat a
  `{job_id}` prefix as existing **only if `manifest.json` is present**
  — so a partial failure (one object written, crash before the marker)
  yields an invisible prefix, never a half-transcript at a canonical
  key. The marker PUT is the linearization point; re-running a failed
  job overwrites the partial objects then re-writes the marker.
- **Cache philosophy.** `result.raw.json` is retained in S3 so a
  re-format (timestamp toggle, speaker relabel) never re-bills
  AssemblyAI — same intent as the F3 versioned cache.
- **Vendor API calls copied byte-for-byte** from a working call or a
  context7 fetch within the implementing PR (see Reference calls).
- **HTTP mocks assert request body shape** (`json_params_matcher` or
  equivalent), not just URL+method.

### Feature-specific decisions (ADR-style decision log)

> This table is the decision record the user asked for: a future-you
> modification anchor and an interview-prep source. Each row = one
> STAR-able decision. Per the repo's teaching-register convention, the
> per-slice `docs/learn/` explainers and `interview-prep.md` STAR hooks
> are drafted at each slice PR's ship time and draw *from this table* —
> this is the source of truth, not a competing record.

| # | Decision | Options considered | Choice | Why (links constitution / brainstorm turn) | Where it can change |
|---|---|---|---|---|---|
| D1 | Spec granularity | (a) one mega-spec; (b) decompose into 7a/7b/7c with a direction doc; (c) start narrower, localhost-first | **(a) mega-spec, internally sliced** | User chose A explicitly; accepted longer doc + internal slice markers as the tradeoff | Slices can be re-ordered/split without changing this spec |
| D2 | Deployment architecture | (a) pure serverless Lambda+Step Functions; (b) hybrid Lambda+Fargate; (c) App Runner monolith | **(a) pure serverless** | $0-idle + AWS-learning + multi-user goals all point at (a); AssemblyAI's submit-then-poll fits Step Functions Wait+Loop so the 15-min Lambda cap is never load-bearing | If faster-whisper-in-cloud ever needed (it won't be), Fargate slice would be added separately |
| D3 | User population | (a) closed family forever; (b) invite-only group; (c) public sign-up | **(b) invite-only** | "me + wife to start, possibly extended later" — (a) forecloses extension, (c) is YAGNI for 1 known extra user | Cognito self-service sign-up is a config change → (c) later |
| D4 | Who pays for AssemblyAI | B(i) you-pay + per-user caps; B(ii) bring-your-own-key | **B(i)** | Friction-free for the non-technical secondary user; bounded blast radius via per-user cap; small DynamoDB field vs. per-user key vault | Switch to BYOK if user list grows past ~5; the secrets abstraction (D11) eases this |
| D5 | CLI ↔ UI relationship | (a) coexistence; (b) cloud-canonical, CLI thin client; (c) CLI dual-mode `--local/--remote` | **(a) coexistence ("Reading 1")** | Preserves constitution local-first $0; library boundary already clean; Drive is the bridge for cross-surface visibility | Reading 2 (`--remote`) is a reversible future addition if unified visibility ever outweighs dual-path cost |
| D6 | Sources in hosted UI | all four / Drive+YouTube only / upload only | **All four (YouTube captions+audio, Drive URL, local upload)** | Source modules already written; captions is the only $0 non-local path; Drive passthrough is near-free to wire | Per-source guardrails are env-config tunable |
| D7 | Output + viewer | S3+viewer / Drive-primary / both | **Both: S3 primary + in-app viewer + optional Drive** | Constitution says outputs flow into Obsidian/NotebookLM/Drive; viewer needed for the read-now loop; optional Drive avoids forcing Google scope on every user | Viewer fidelity can grow; Drive stays optional |
| D8 | Auth | Cognito+Google fed / Cognito email-pw / pure Google OAuth | **Cognito + Google federated IdP** for app sign-in; **separate Google OAuth authorization-code flow** for the Drive token | One-click Cognito sign-in for secondary-user UX, highest AWS-learning surface. Codex P1 correction: Cognito federation yields Cognito user-pool tokens only and does **not** reliably surface the upstream Google access/refresh token — so Drive access is a **distinct** Google OAuth authorization-code consent (offline → refresh token), opt-in when the user first enables Drive upload. Not "one consent". | IdP set is Cognito config; email/pw can be added; Drive-token flow pinned in Reference calls |
| D9 | Frontend stack | Vite+React+TS+TanStack Query / Next.js+Amplify / SvelteKit | **Vite + React + TS + TanStack Query, S3+CloudFront** | Modern-frontend learning without framework tax; doesn't hide AWS (vs Amplify); TanStack Query is a natural fit for the poll lifecycle; React-first serves interview-prep | Hosting can move to Amplify later without app rewrite |
| D10 | Cost-gate mechanism | SF callback token / poll-inside-SF / synchronous Lambda wait | **Step Functions callback token, 24h heartbeat** | $0 while paused; survives tab close; clean resume via API GW → SendTaskSuccess/Failure | Timeout window is config (24h default) |
| D11 | Secrets backend | SSM Parameter Store / Secrets Manager / both behind abstraction | **Both behind a `SecretsProvider` abstraction; default `ssm` ($0)** | Mirrors the repo's existing provider-registry pattern; cost-sensitive default; one config flip to switch; richer learning artifact | `TRANSCRIBER_SECRETS_BACKEND` env value |
| D12 | Notification | SES email + polling / WebSocket / poll-only | **SES email + in-app polling, no WebSocket** | Polling+email covers every real case at $0 idle; WebSocket is unjustified connection-mgmt infra for minute-scale jobs | WebSocket addable if sub-second ever matters (won't) |
| D13 | Local guided runbook home | separate follow-up / inside Phase 7 spec | **Inside Phase 7 spec as slice 7e** | User instruction (overrode the recommend-separate); kept as an isolated slice with zero AWS coupling so write-plan stays clean | Independently shippable; can ship first |
| D14 | Default monthly cap | $5 / $10 / $20 | **$5/user (admin-tunable)** | ≈9h AssemblyAI universal-3-pro; tight feedback loop for cost-sensitivity; admin can raise per-user | `monthly_budget_usd` per user |
| D15 | Overshoot policy | refund-anyway / eat+alert>$0.50 / hard-reject-on-uncertainty | **Eat overshoot, log + alarm > $0.50** | Keeps the cap a real ceiling without hostile UX | Threshold is config |
| D16 | Slice order | 7a-first / 7b-first / 7e-first | **7e → 7a → 7b → 7c → 7d** | 7e is zero-AWS and independently valuable (quick win); 7a proves the AWS wire-up small before the cost surface (7b) | 7e is fully independent (any order). 7a is the auth+API scaffold; 7b/7c/7d all depend on 7a, and 7c/7d additionally depend on 7b's pipeline. Order within 7a→7d is otherwise fixed by these deps. |

## Reference calls (verbatim)

> CLAUDE.md guardrail is hard: vendor API calls must be copied from a
> working call or a context7 fetch performed **within the implementing
> slice's PR**. This section states the discipline and the carry-forward
> sources; the two NEW integration shapes MUST be pinned here (edited
> into this file) before the relevant slice's implementation code is
> written — never paraphrased from memory or training data.

### AssemblyAI (carry-forward — already pinned)

**Source:** existing pinned blocks in
`specs/2026-05-04-drive-source-passthrough/requirements.md`
§"Reference calls (verbatim)" (the `audio_url` passthrough shape) and
`specs/2026-05-13-youtube-audio-fallback/requirements.md` (upload +
poll shape). PR #12's incident and PR #13's structural defence apply.
**Status:** REUSE verbatim for the Drive-passthrough and
upload-from-bytes paths.

**NEW variant to pin at slice 7c implementation:** AssemblyAI ingesting
from a **presigned S3 GET URL** (local-upload path) — same `/v2/transcript`
shape with `audio_url` = the presigned S3 URL. Confirm via context7 that
`audio_url` accepts a time-limited presigned S3 URL and capture the
retrieval date here before writing 7c code.

### Google Drive token acquisition (NEW — pin at 7a/7c)

**Decision (resolves Codex P1).** Cognito + Google federated IdP
provides **app identity / sign-in only**: it yields Cognito user-pool
tokens, **not** the upstream Google access/refresh token, and Cognito
does not reliably surface the IdP token. Drive API access therefore
uses a **separate, explicit Google OAuth 2.0 authorization-code flow**,
distinct from sign-in:

- Scope `https://www.googleapis.com/auth/drive.file`, with
  `access_type=offline` + `prompt=consent` to obtain a refresh token.
- Triggered only when the user first enables Drive upload (7c) — not
  during Cognito sign-in.
- The authorization code is exchanged **server-side**; the refresh
  token is stored KMS-encrypted (DynamoDB `SK=#GOOGLE_TOKENS`); access
  tokens are minted from the refresh token on demand by the
  drive-upload Lambda.
- `POST /users/me/google-tokens` carries the authorization code (or
  the server completes the redirect exchange). It **never** depends on
  a Cognito-surfaced IdP token.

**Required before slice 7a/7c implementation:** context7 fetch for the
verbatim Google OAuth 2.0 authorization-code shapes (authorize-URL
params, token-endpoint code exchange, refresh exchange) **and** the
exact Cognito User Pool Google-IdP configuration used for identity.
Capture verbatim request/response shapes + retrieval date in this
section before that code is written.

#### 7a pins (identity only) — context7 /aws/aws-cdk, retrieved 2026-05-16

Construct shapes below are verbatim from the AWS CDK README via
context7 `/aws/aws-cdk` (retrieved 2026-05-16). The CDK README ships
TypeScript snippets only; the CDK Python API is JSII-codegenerated
from the same construct spec, so the mechanical mapping is: same
construct/class names, props become snake_case keyword arguments
(`clientId` → `client_id`, `clientSecretValue` → `client_secret_value`,
`attributeMapping` → `attribute_mapping`, `userPool` → `user_pool`,
`jwtAudience` → `jwt_audience`). Task 8 codes the Python constructs by
applying that rule to the verbatim TS below — no hand-rewrite from
memory. The Cognito **federated sign-in Lambda trigger event payload**
is a Cognito service contract not documented in `/aws/aws-cdk`; it is
pinned verbatim from the AWS Cognito Developer Guide (URLs + retrieval
date inline below), per the verifiability intent of the CLAUDE.md
guardrail.

- Cognito UserPoolIdentityProviderGoogle (Python) — verbatim construct signature + attribute_mapping shape:

  Verbatim from context7 `/aws/aws-cdk`
  (`packages/aws-cdk-lib/aws-cognito/README.md`), retrieved 2026-05-16.
  Construct + Secrets Manager client secret:

  ```ts
  const userpool = new cognito.UserPool(this, 'Pool');
  const secret = secretsmanager.Secret.fromSecretAttributes(this, "CognitoClientSecret", {
      secretCompleteArn: "arn:aws:secretsmanager:xxx:xxx:secret:xxx-xxx"
  }).secretValue

  const provider = new cognito.UserPoolIdentityProviderGoogle(this, 'Google', {
    clientId: 'amzn-client-id',
    clientSecretValue: secret,
    userPool: userpool,
  });
  ```

  Verbatim `attributeMapping` shape (mapping `email` /
  `email_verified` from the Google IdP), same source:

  ```ts
  const userpool = new cognito.UserPool(this, 'Pool');

  new cognito.UserPoolIdentityProviderGoogle(this, 'google', {
    userPool: userpool,
    clientId: 'google-client-id',
    attributeMapping: {
      email: cognito.ProviderAttribute.GOOGLE_EMAIL,
      emailVerified: cognito.ProviderAttribute.GOOGLE_EMAIL_VERIFIED, // you can mapping the `email_verified` attribute.
    },
  });
  ```

  Verbatim general `attributeMapping` pattern (standard + custom +
  `other()` for non-predefined attributes), same source (shown for the
  Amazon IdP in the README; the `attributeMapping`/`ProviderAttribute`
  shape is identical across `UserPoolIdentityProvider*` constructs):

  ```ts
  attributeMapping: {
    email: cognito.ProviderAttribute.AMAZON_EMAIL,
    website: cognito.ProviderAttribute.other('url'), // use other() when an attribute is not pre-defined in the CDK
    custom: {
      // custom user pool attributes go here
      uniqueId: cognito.ProviderAttribute.AMAZON_USER_ID,
    },
  },
  ```

  Python mapping (per the codegen rule above): class
  `aws_cdk.aws_cognito.UserPoolIdentityProviderGoogle`; kwargs
  `client_id=`, `client_secret_value=` (a
  `aws_cdk.SecretValue`), `user_pool=`, `attribute_mapping=` (an
  `aws_cdk.aws_cognito.AttributeMapping` / dict), with
  `aws_cdk.aws_cognito.ProviderAttribute.GOOGLE_EMAIL`,
  `.GOOGLE_EMAIL_VERIFIED`, and `ProviderAttribute.other('...')`.

- Cognito federated sign-in Lambda trigger that gates un-invited users — trigger name + verbatim event payload shape:

  **Trigger: Pre sign-up Lambda trigger, `triggerSource =
  "PreSignUp_ExternalProvider"`.** Evidence (verbatim from AWS Cognito
  Developer Guide
  `cognito-user-pools-working-with-lambda-triggers.html`, section
  "Lambda triggers for federated users", retrieved 2026-05-16):

  > **Federated user trigger sources**
  > - **First sign-in**
  >   - **Lambda trigger:** Pre sign-up / **Trigger source:** `PreSignUp_ExternalProvider`
  >   - **Lambda trigger:** Post confirmation / **Trigger source:** `PostConfirmation_ConfirmSignUp`
  >   - **Lambda trigger:** Pre token generation / **Trigger source:** `TokenGeneration_HostedAuth`
  > - **Subsequent sign-ins**
  >   - **Lambda trigger:** Pre authentication / **Trigger source:** `PreAuthentication_Authentication`
  >   - **Lambda trigger:** Post authentication / **Trigger source:** `PostAuthentication_Authentication`
  >   - **Lambda trigger:** Pre token generation / **Trigger source:** `TokenGeneration_HostedAuth`

  And the triggerSource table (same source):

  > | Trigger | triggerSource value | Event |
  > | Pre sign-up | PreSignUp_SignUp | Pre sign-up. |
  > | Pre sign-up | PreSignUp_AdminCreateUser | Pre sign-up when an admin creates a new user. |
  > | Pre sign-up | PreSignUp_ExternalProvider | Pre sign-up for external identity providers. |

  So the gate Lambda is the **Pre sign-up** trigger, distinguishing
  `triggerSource == "PreSignUp_ExternalProvider"` (Google federated
  first sign-in) from `PreSignUp_SignUp` (self-service) and
  `PreSignUp_AdminCreateUser`. Returning an error from the function
  denies the sign-up — verbatim from the same guide: "If your Lambda
  function doesn't return the request and response parameters to
  Amazon Cognito, or returns an error, the authentication event
  doesn't succeed. You can return an error in your function to prevent
  a user's sign-up, authentication, token generation, or any other
  stage of their authentication flow that invokes Lambda trigger." For
  federated users the docs note (verbatim): "your pre sign-up trigger
  can automatically confirm users for the `PreSignUp_SignUp` trigger
  source, but return the event unchanged for external and
  administrator-created users."

  Common Lambda trigger event envelope — verbatim from
  `cognito-user-pools-working-with-lambda-triggers.html` ("User pool
  Lambda trigger event"), retrieved 2026-05-16:

  ```json
  {
      "version": "{{string}}",
      "triggerSource": "{{string}}",
      "region": {{AWSRegion}},
      "userPoolId": "{{string}}",
      "userName": "{{string}}",
      "callerContext":
          {
              "awsSdkVersion": "{{string}}",
              "clientId": "{{string}}"
          },
      "request":
          {
              "userAttributes": {
                  "{{string}}": "{{string}}",
                  ....
              }
          },
      "response": {}
  }
  ```

  Pre sign-up trigger-specific request/response — verbatim from
  `user-pool-lambda-pre-sign-up.html` ("Pre sign-up Lambda trigger
  parameters"), retrieved 2026-05-16:

  ```json
  {
      "request": {
          "userAttributes": {
              "{{string}}": "{{string}}",
              . . .
          },
          "validationData": {
              "{{string}}": "{{string}}",
              . . .
           },
          "clientMetadata": {
              "{{string}}": "{{string}}",
              . . .
           }
      },

      "response": {
          "autoConfirmUser": "{{boolean}}",
          "autoVerifyPhone": "{{boolean}}",
          "autoVerifyEmail": "{{boolean}}"
      }
  }
  ```

  Concrete example input event (verbatim, same guide, "Client
  metadata" section — shown with `PreSignUp_SignUp`; the envelope keys
  are identical for `PreSignUp_ExternalProvider`, only `triggerSource`
  and the `userAttributes` provided by attribute mapping differ):

  ```json
  {
      "callerContext": {
          "awsSdkVersion": "aws-sdk-unknown-unknown",
          "clientId": "1example23456789"
      },
      "region": "us-west-2",
      "request": {
          "clientMetadata": {
              "GeoLocation": "Netherlands (Kingdom of the) [NL]",
              "IpAddress": "192.0.2.252"
          },
          "userAttributes": {
              "email": "mary_major@example.com",
              "name": "Mary",
              "phone_number": "+12065551212"
          },
          "validationData": null
      },
      "response": {
          "autoConfirmUser": false,
          "autoVerifyEmail": false,
          "autoVerifyPhone": false
      },
      "triggerSource": "PreSignUp_SignUp",
      "userName": "mary_major2",
      "userPoolId": "us-west-2_EXAMPLE",
      "version": "1"
  }
  ```

  Reject pattern (Python) — verbatim from `user-pool-lambda-pre-sign-up.html`
  ("Deny sign-up if user name has fewer than five characters"),
  retrieved 2026-05-16; raising rejects the sign-up:

  ```python
  def lambda_handler(event, context):
      if len(event['userName']) < 5:
          raise Exception("Cannot register users with username less than the minimum length of 5")
      # Return to Amazon Cognito
      return event
  ```

  Note for Task 7: for a federated Google user, `userName` is the
  Cognito-assigned federated username (e.g. `Google_<sub>`), not the
  email; gate logic must read the invited email from
  `event['request']['userAttributes']['email']` (populated by the
  IdP attribute mapping pinned above) and branch on
  `event['triggerSource'] == 'PreSignUp_ExternalProvider'`.

- API Gateway v2 HTTP API + Cognito JWT authorizer (Python) — verbatim construct shape:

  Verbatim from context7 `/aws/aws-cdk`
  (`packages/aws-cdk-lib/aws-apigatewayv2-authorizers/README.md`),
  retrieved 2026-05-16 — Cognito User Pool authorizer for HTTP API:

  ```ts
  import * as cognito from 'aws-cdk-lib/aws-cognito';
  import { HttpUserPoolAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
  import { HttpUrlIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';

  const userPool = new cognito.UserPool(this, 'UserPool');

  const authorizer = new HttpUserPoolAuthorizer('BooksAuthorizer', userPool);

  const api = new apigwv2.HttpApi(this, 'HttpApi');

  api.addRoutes({
    integration: new HttpUrlIntegration('BooksIntegration', 'https://get-books-proxy.example.com'),
    path: '/books',
    authorizer,
  });
  ```

  Verbatim generic JWT authorizer variant (OIDC issuer + audience),
  same source — usable if a raw issuer URL is preferred over the
  Cognito-specific wrapper:

  ```ts
  import { HttpJwtAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
  import { HttpUrlIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';

  const issuer = 'https://test.us.auth0.com';
  const authorizer = new HttpJwtAuthorizer('BooksAuthorizer', issuer, {
    jwtAudience: ['3131231'],
  });

  const api = new apigwv2.HttpApi(this, 'HttpApi');

  api.addRoutes({
    integration: new HttpUrlIntegration('BooksIntegration', 'https://get-books-proxy.example.com'),
    path: '/books',
    authorizer,
  });
  ```

  Verbatim default-authorizer + scopes variant, same source:

  ```ts
  import { HttpJwtAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';

  const issuer = 'https://test.us.auth0.com';
  const authorizer = new HttpJwtAuthorizer('DefaultAuthorizer', issuer, {
    jwtAudience: ['3131231'],
  });

  const api = new apigwv2.HttpApi(this, 'HttpApi', {
    defaultAuthorizer: authorizer,
    defaultAuthorizationScopes: ['manage:books'],
  });
  ```

  Python mapping (per the codegen rule above): classes
  `aws_cdk.aws_apigatewayv2.HttpApi`,
  `aws_cdk.aws_apigatewayv2_authorizers.HttpUserPoolAuthorizer`
  (positional `id`, `pool`), `HttpJwtAuthorizer` (positional `id`,
  `jwt_issuer`, kwarg `jwt_audience=`),
  `aws_cdk.aws_apigatewayv2_integrations.HttpUrlIntegration`;
  `http_api.add_routes(path=..., integration=..., authorizer=...)`;
  `HttpApi(..., default_authorizer=..., default_authorization_scopes=[...])`.

(Drive authorization-code / refresh-token shapes remain deferred to slice 7c, per the parent section.)

### yt-dlp / youtube-transcript-api (carry-forward)

**Source:** `specs/2026-05-13-youtube-audio-fallback/requirements.md`
and `specs/2026-05-12-youtube-captions-source/requirements.md`
§"Reference calls (verbatim)". REUSE verbatim; the Lambda packaging of
yt-dlp (binary/ffmpeg layer) is an infra concern, not a shape change.

## Output contracts

- **Markdown output:** unchanged from the existing
  `formatters/markdown.py` contract — same YAML frontmatter
  (`source_kind`, `provider`, `model`, `duration`, `cost_usd`,
  speaker/timestamp fields). The hosted pipeline reuses the formatter
  verbatim; no new frontmatter fields.
- **S3 layout** (a `{job_id}` prefix is reader-visible **only once its
  `manifest.json` exists** — see Atomic output writes):
  - `transcripts-bucket/{cognito_sub}/{job_id}/transcript.md`
  - `transcripts-bucket/{cognito_sub}/{job_id}/result.raw.json`
  - `transcripts-bucket/{cognito_sub}/{job_id}/manifest.json`
    (commit marker, written **last**; presence = job committed)
  - `temp-audio-bucket/{cognito_sub}/{job_id}.{ext}` (lifecycle: delete
    after 14 days)
- **DynamoDB single-table** (PK/SK + GSI1 token-lookup + GSI2 admin
  scan): user profile (`SK=#PROFILE`), job records
  (`SK=JOB#{iso_ts}#{job_id}`), KMS-encrypted Google tokens
  (`SK=#GOOGLE_TOKENS`). Field-level shapes per the design (budget,
  settlement_state ∈ {reserved, settled, refunded, failed}, job status
  ∈ {queued, awaiting_cost, running, done, failed, cancelled}).
- **API (API Gateway HTTP API, Cognito-authorized):**
  `GET /transcripts`, `GET /transcripts/{id}`, `DELETE /transcripts/{id}`,
  `POST /jobs` (submit), `GET /jobs/{id}` (status poll),
  `POST /jobs/{id}/confirm` (cost gate resume),
  `POST /users/me/google-tokens`, `GET /users/me` (budget/settings),
  admin: `POST /admin/users`, `PATCH /admin/users/{sub}`.
- **CLI exit codes / local outputs:** unchanged. Slice 7e adds no new
  output contract — it only orchestrates the existing `transcribe`
  command.

## F-contract status

| Contract | Status | Notes |
|---|---|---|
| F1 sync | **EXTENDED** | Library stays sync; orchestration event-driven at the hosting boundary only. PLAN.md §F1 amended (see Constraints). The amendment expands the named sync-only set to add `destinations/` + `core/`; the implementing PR **must** update CLAUDE.md's guardrail line in lockstep (see the §F1 row note in Constraints). |
| F2 PreparedMedia | **ADAPTED** | Same dataclass and source contract, but F2's `local_path: Path` "always present" invariant does **not** hold for Lambda-initiated Drive-URL jobs — the `remote_url` passthrough path is used and `local_path` is `None` or a Lambda `/tmp` path. Implementers must not assume `local_path` is populated in the hosted context. |
| F3 cache key | **ADAPTED** | Preserves F3's *intent* (retain the raw result so a re-format never re-bills) but **not** its contract: the hosted path stores `result.raw.json` keyed by `{cognito_sub}/{job_id}` (job identity), **not** the versioned `audio_sha256 + provider + model + revision + language + vad_mode + schema` composite with lookup-by-key. Do **not** reuse the `~/.cache/transcriber/` `CacheKey` mechanics in Lambda. |
| F4 two-gate spend | **EXTENDED** | Hosted adds Gate 3 (per-user cap). CLI stays two-gate. PLAN.md §F4 amended. |
| F5 RunWorkspace | **ADAPTED** | Lambda `/tmp` + temp-audio S3 bucket play the workspace role; atomic-write principle preserved via staged objects + a last-written `manifest.json` commit marker (see Atomic output writes / Codex P2). |
| F6 model preflight | **N/A** | AssemblyAI-only in hosted; no local model. faster-whisper explicitly out (Non-goals). |
| F7 test strategy | **EXTENDED** | Adds Lambda unit tests, Step Functions local execution, `moto`-mocked AWS; integration lane stays opt-in (`SSM_INTEGRATION`). |
| F8 observability | **EXTENDED** | CloudWatch structured logs; no secrets; budget/provider decisions at INFO — same rule, new sink. |

## Dependencies added

Runtime (hosted Lambdas / IaC — not added to the core CLI `pyproject.toml`
unless shared): `boto3`, an IaC tool (AWS CDK or SAM — chosen at
`write-plan`), plus the existing `assemblyai`/`yt-dlp`/
`youtube-transcript-api`/`google-api-python-client` already in the repo.
Frontend (separate `web/` workspace): `vite`, `react`, `typescript`,
`@tanstack/react-query`, an HTTP client, a markdown renderer.

Dev: `moto` (AWS mocking), Step Functions Local, `pytest` lanes as F7.

No new vendor-key env var beyond existing `ASSEMBLYAI_API_KEY` (moves
into the `SecretsProvider`-backed store). New config:
`TRANSCRIBER_SECRETS_BACKEND` (`ssm`|`secrets_manager`, default `ssm`).
Google OAuth client config reused from the existing
`GOOGLE_OAUTH_CLIENT_ID`/`SECRET` slots in `.env.example`.

## Tracking convention (mega-spec → issues)

`docs/ai/runbooks/tracking.md` mandates one issue per phase/slice. A
single multi-slice mega-spec needs an explicit rule so the board does
not stay misleading for the whole multi-slice build:

- Issue **#37** is the **Phase 7 parent anchor**. It is referenced
  (`Refs #37`) by the spec PR and every slice PR; it is **not**
  auto-closed by any single slice. It closes only when all slices have
  landed.
- Open **one issue per implementation slice** — 7a, 7b, 7c, 7d —
  **before 7a implementation begins**. 7e is already tracked (shipped
  in PR #39, `Refs #37`); a 7e issue is optional/retroactive.
- Each slice's implementation PR carries `Closes #<that-slice-issue>`
  (auto-closes its own card) **and** `Refs #37` (keeps the parent
  visible). No slice PR uses `Closes #37`.
- Spec PR #38 uses `Refs #37` only (a spec PR never auto-closes the
  slice/phase issue, per tracking.md).

## Slice map (implementation units within this mega-spec)

- **7e — Guided local-transcribe runbook** (ships first; zero AWS):
  `docs/ai/runbooks/transcribe-local.md` + a thin
  `.claude/commands/transcribe-local.md` pointer + two
  `docs/ai/README.md` routing rows. The non-Claude tool adapters
  (`AGENTS.md`, `.cursorrules`, `.github/copilot-instructions.md`,
  `GEMINI.md`) need **no** edit — they already indirect via
  `docs/ai/README.md`, so the routing table is the AI-agnostic surface
  (reconciliation recorded in `plan-7e.md`). No Python change. Verify:
  from Claude Code AND Codex, the runbook walks the user to a correct
  `uv run ssm-transcriber …` without flag recall. **Shipped in PR #39.**
- **7a — Auth scaffold + S3 viewer:** Cognito+Google fed, CloudFront+S3
  SPA, API GW Cognito authorizer, list/get/delete transcript Lambdas,
  seeded S3 fixture. Verify: Google sign-in → see + read a seeded
  transcript; un-invited account rejected.
- **7b — Submit + cost gate + status:** Step Functions state machine,
  jobs table + reserve/settle, cost-gate modal, live status page.
  Sources: YouTube captions+audio, Drive URL. Verify: submit YouTube →
  approve cost → watch stages → markdown in S3 + viewer.
- **7c — Local upload + Drive output + email:** presigned S3 PUT
  (≤500MB), optional Drive upload via the user's Google token, SES
  notifications. Verify: upload file → transcribe → email → optional
  Drive landing.
- **7d — Admin / invite / budget UI:** admin Lambda (invite, set cap,
  usage, suspend), user settings page. Verify: invite 2nd user, set
  cap, observe Gate-3 enforcement and refund/settlement transitions.

Plus a cross-cutting **AWS teardown runbook**
(`docs/ai/runbooks/aws-teardown.md`): IaC `destroy` → literal $0;
`deploy` → restore. Documented as a first-class cost lever and
IaC-lifecycle learning artifact.

## Failure behaviour

| Failure | Behaviour | Budget |
|---|---|---|
| Probe fails (bad URL, >3h video, geo-block, >2GB Drive, >500MB upload) | SF ends; job `failed`; reason in UI + email; no cost gate | Nothing reserved |
| Gate 3: estimate **or Drive conservative ceiling** > `remaining_budget_usd` (Scenarios 9, 6) | `reserve-budget` conditional write fails; job `failed`; message "estimated/maximum $X exceeds your remaining $Y this month; ask the admin to raise your cap"; no AssemblyAI call | Nothing reserved (conditional write never succeeded) |
| User cancels at cost gate / 24h timeout | `SendTaskFailure` / heartbeat → job `cancelled` | Full refund |
| AssemblyAI returns error status | poll Choice → fail path; raw error logged | Settle to actual (≈$0 if AAI didn't bill) |
| Lambda crash mid-AAI (unknown billing) | SF Catch → job `failed`, `settlement_state=failed` | NOT refunded; CloudWatch alarm; admin reconciles |
| Drive upload fails (post-transcription) | Transcript safe in S3 + viewer; job `done` + Drive-warning banner | Already settled |
| SES send fails | Logged, non-fatal; user sees state on next visit | Unaffected |

## Cost floor (honest — not literally $0 unless torn down)

- S3 storage: pennies (text durable; audio auto-deleted 14d).
- Route 53: ~$0.50/mo **only if** a custom domain is attached. v1
  default: CloudFront default domain = $0.
- CloudWatch Logs: ≈free at this volume with 14-day retention.
- Cognito: free tier 50k MAU → $0 here.
- Secrets backend: SSM Parameter Store SecureString = $0 (the default,
  D11); Secrets Manager ≈ $0.80/mo for 2 secrets (opt-in).
- **Realistic idle floor:** ≈$0 (Parameter Store default). Teardown
  runbook → literal $0 for long dormancy.
