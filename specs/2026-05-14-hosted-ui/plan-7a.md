# Phase 7 Slice 7a — Auth Scaffold + S3 Viewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **LIFECYCLE GATE — read before executing.** Per `docs/ai/runbooks/gstack-superpowers-workflow.md` Loop A, this plan does **not** get executed directly after it is written. The next step after this file exists is: **open the per-slice plan PR (`Refs #37`), external multi-vendor review on that PR, merge, board move — *then* subagent execution.** Do not jump to subagent-driven-development from the writing-plans handoff; that would invert the two-PR SDD lifecycle this repo mandates (`docs/ai/runbooks/tracking.md` §"Lifecycle").

**Goal:** An invited user signs in with Google through Cognito, sees their existing transcripts newest-first, opens one to read its markdown, and can delete it — on a pure-serverless AWS stack that tears down to ≈$0.

**Architecture:** AWS CDK (Python) provisions Cognito (Google federated IdP, identity only), an invite-gate Lambda trigger, S3 (transcripts + SPA hosting), CloudFront, a DynamoDB single-table (only `#PROFILE` items in 7a), an API Gateway HTTP API with a Cognito JWT authorizer, and three transcript Lambdas (list/get/delete). A Vite+React+TS SPA hosts the sign-in callback, dashboard, and viewer. The existing `src/transcriber/` sync library is untouched; all hosted code is the orchestration boundary under `src/transcriber/hosted/`.

**Tech Stack:** AWS CDK v2 (Python), `boto3`, `moto` + `aws-cdk-lib/assertions` (backend/infra TDD), Vite + React + TypeScript + TanStack Query + Vitest/RTL (frontend), Cognito + Google IdP, API Gateway HTTP API, DynamoDB single-table, S3 + CloudFront.

---

## ADR-0 (pinned) — IaC tool: AWS CDK (Python)

| Field | Value |
|---|---|
| **Decision** | Infrastructure for Phase 7 (7a–7d) is authored with **AWS CDK v2 in Python**. |
| **Options considered** | (a) AWS CDK (Python); (b) AWS SAM. |
| **Choice** | **(a) AWS CDK (Python).** |
| **Why** | This slice's infra is auth + CDN heavy: federated Cognito (Google IdP), CloudFront+S3 SPA, API GW Cognito authorizer, a Step Functions Wait+Loop machine (7b). CDK L2 constructs collapse exactly these (`UserPoolIdentityProviderGoogle`, `CognitoUserPoolsAuthorizer`, fluent Step Functions chains) where SAM has no serverless abstraction for the user pool, Google federation, or CloudFront and degrades to hand-written raw CloudFormation. CDK keeps infra in Python (same language as the app; OO model maps to the author's Java background) and ships `assertions.Template` for infra unit tests the spec's F7 lane already calls for. `cdk synth` still emits CloudFormation for learning; `cdk destroy` is the spec's $0 lever. Grounded in Context7 fetch of `/aws/aws-cdk` and `/aws/serverless-application-model`, 2026-05-16. |
| **Rejected: SAM** | SAM teaches raw CloudFormation more directly and `sam local invoke` is the best local-Lambda story — but this stack's hard parts (Cognito federation, CloudFront) become verbose hand-written CFN, and the spec already covers local testing via `moto` + Step Functions Local, so SAM's edge does not pay for its YAML tax here. |
| **Where it can change** | Reversible per-slice in principle, but in practice locked once 7a infra lands. Revisit only if a future slice needs heavy non-serverless resources (it won't — D2 pure-serverless). |

---

## Scope (7a only)

**In:** Cognito user pool + Google federated IdP (identity/auth only — **no Drive scope**), invite-gate Lambda trigger (un-invited Google account rejected), API GW HTTP API + Cognito JWT authorizer, `list`/`get`/`delete` transcript Lambdas reading S3 with the `manifest.json` commit-marker visibility rule, DynamoDB single-table with **only `#PROFILE`** items, S3 transcripts bucket + S3/CloudFront SPA hosting, the React SPA (sign-in callback, dashboard list + budget pill, viewer, delete), a seeded invited-user profile + seeded transcript fixture, the constitution amendments + CLAUDE.md lockstep + teaching-register docs that ship with this slice, and the AWS teardown runbook (first AWS lands here).

**Out (do not build in 7a):** job submission / cost gate / status / Step Functions (7b), `temp-audio` bucket (7b/7c), local upload + presigned PUT (7c), Drive output + the Google OAuth authorization-code/refresh-token flow + KMS token storage (7c), SES email (7c), admin/invite UI + Gate-3 budget *enforcement* + usage math (7d). The dashboard **budget pill in 7a is a pure profile-field render** (`monthly_budget_usd`) — no usage accounting, no enforcement.

**F-contract posture (from spec §F-contract status):** F1 EXTENDED (library stays sync; `src/transcriber/hosted/` is the event-driven orchestration boundary — and the CLAUDE.md guardrail line is edited in lockstep, Task G2). F2/F3/F5 ADAPTED, F6 N/A, F7/F8 EXTENDED. The 7a Lambdas import nothing that adds `async def` to `src/transcriber/{sources,providers,formatters,destinations,core}/`.

## Repository layout introduced

```
src/transcriber/hosted/            # NEW — orchestration boundary (outside the F1 sync-only named set)
  __init__.py
  s3keys.py                        # S3 key/prefix helpers + manifest-visibility rule
  errors.py                        # hosted-side error → HTTP status mapping
  handlers/
    __init__.py
    list_transcripts.py            # GET /transcripts
    get_transcript.py              # GET /transcripts/{id}
    delete_transcript.py           # DELETE /transcripts/{id}
    invite_gate.py                 # Cognito Lambda trigger (federated sign-in gate)
infra/                             # NEW — self-contained CDK Python app (NOT in core pyproject runtime)
  app.py
  cdk.json
  requirements.txt
  README.md
  stacks/__init__.py
  stacks/hosted_stack.py
  tests/__init__.py
  tests/test_hosted_stack.py       # aws_cdk.assertions.Template
web/                               # NEW — Vite + React + TS SPA workspace
  package.json  index.html  vite.config.ts  tsconfig.json
  src/{main.tsx,App.tsx,auth.ts,api.ts,manifest.ts,components/*}
  src/__tests__/*.test.ts(x)       # Vitest + RTL (non-trivial logic only)
tests/unit/hosted/                 # NEW — pytest + moto for the Lambda handlers
  __init__.py
  test_s3keys.py  test_list_transcripts.py  test_get_transcript.py
  test_delete_transcript.py  test_invite_gate.py
docs/ai/runbooks/aws-teardown.md   # NEW — cross-cutting $0 lever (first AWS lands in 7a)
docs/learn/prs/pr-0NN-7a-auth-scaffold-impl.md   # teaching-register (Task G3)
specs/2026-05-14-hosted-ui/validation.md         # filled by Group F
```

**Deployability discipline:** every Group from B onward leaves `cd infra && cdk synth` green and (for the engineer with AWS creds) `cdk deploy` succeeding incrementally. Do not batch all infra then deploy once.

---

## Group A — Pre-flight: spec pin + scaffolding

### Task 0: Pin the 7a vendor/Cognito shapes into the merged spec (context7, before any code)

**Files:**
- Modify: `specs/2026-05-14-hosted-ui/requirements.md` (§"Reference calls (verbatim)" → "Google Drive token acquisition (NEW — pin at 7a/7c)")

This is a **spec amendment that ships in the 7a impl PR**, mandated verbatim by requirements.md:229-234 ("Capture verbatim request/response shapes + retrieval date in this section before that code is written"). Only the **7a-relevant** shapes are pinned now; the Drive authorization-code/refresh shapes stay deferred to 7c.

- [ ] **Step 1: context7 fetch — Cognito Google IdP construct + federated-signin trigger**

Use the Context7 MCP (per the repo's ctx7 rule). Fetch from `/aws/aws-cdk`:
1. `aws_cognito.UserPoolIdentityProviderGoogle` Python construct: required props (`client_id`, `client_secret_value` / `client_secret`, `scopes`, `attribute_mapping`), and how it attaches to a `UserPool`.
2. `aws_cognito.UserPool` Lambda triggers for **federated sign-in**: the exact trigger that fires for a third-party (Google) federated user and can **reject an un-invited user**, and that trigger's **event payload shape** (do not assume Pre-Sign-up semantics — verify which trigger fires for federated vs. self-service and capture the event keys: `triggerSource`, `request.userAttributes`, `userName`, etc.).
3. `aws_apigatewayv2` / `aws_apigatewayv2_authorizers` HTTP API + JWT (Cognito) authorizer Python construct shape.

- [ ] **Step 2: Pin verbatim into requirements.md**

Append a subsection to "Google Drive token acquisition (NEW — pin at 7a/7c)" titled exactly:

```
#### 7a pins (identity only) — context7 /aws/aws-cdk, retrieved 2026-05-16

- Cognito UserPoolIdentityProviderGoogle (Python) — verbatim construct signature + attribute_mapping shape:
  <paste verbatim from fetch>
- Cognito federated sign-in Lambda trigger that gates un-invited users — trigger name + verbatim event payload shape:
  <paste verbatim from fetch>
- API Gateway v2 HTTP API + Cognito JWT authorizer (Python) — verbatim construct shape:
  <paste verbatim from fetch>

(Drive authorization-code / refresh-token shapes remain deferred to slice 7c, per the parent section.)
```

Replace each `<paste verbatim …>` with the actual fetched text. Do **not** paraphrase.

- [ ] **Step 3: Commit**

```bash
git add specs/2026-05-14-hosted-ui/requirements.md
git commit -m "docs(spec): pin 7a Cognito/IdP/HTTP-API shapes (context7) before impl"
```

### Task 1: Branch + dependency groups

**Files:**
- Modify: `pyproject.toml` (add a `hosted` dev/test dependency group; keep core runtime deps untouched per spec:289)
- Create: `infra/requirements.txt`

- [ ] **Step 1: Create the slice branch**

```bash
git checkout main && git pull --ff-only
git checkout -b feat/7a-auth-scaffold
```

- [ ] **Step 2: Add a `hosted` optional-dependency group (NOT core runtime)**

In `pyproject.toml`, under `[project.optional-dependencies]`, add a new group below the existing `dev` list. `boto3` and `moto` back the Lambda handler tests; they must not enter the core `dependencies` array (spec:289 — "not added to the core CLI pyproject.toml unless shared").

```toml
hosted = [
    "boto3>=1.34.0",
    "moto[s3,dynamodb,cognitoidp]>=5.0.0",
    "types-boto3>=1.0.0",
]
```

- [ ] **Step 3: mypy + hatchling already cover `src/transcriber/hosted/`**

No edit needed: `mypy_path = "src"` and `[tool.hatch.build.targets.wheel] packages = ["src/transcriber"]` already include the new subpackage. Add a mypy override for boto3 stubs only if `types-boto3` proves insufficient (defer until Task B/D surfaces it).

- [ ] **Step 4: Pin CDK infra deps**

`infra/requirements.txt`:

```
aws-cdk-lib>=2.140.0,<3.0.0
constructs>=10.3.0,<11.0.0
```

- [ ] **Step 5: Verify env and commit**

Run: `uv sync --extra hosted && uv run python -c "import boto3, moto; print('hosted deps OK')"`
Expected: `hosted deps OK`

```bash
git add pyproject.toml infra/requirements.txt
git commit -m "build(7a): add hosted test deps + CDK infra requirements"
```

### Task 2: CDK app skeleton (synth-green, no resources yet)

**Files:**
- Create: `infra/cdk.json`, `infra/app.py`, `infra/stacks/__init__.py`, `infra/stacks/hosted_stack.py`, `infra/tests/__init__.py`, `infra/tests/test_hosted_stack.py`, `infra/README.md`

- [ ] **Step 1: Write the failing infra test**

`infra/tests/test_hosted_stack.py`:

```python
import aws_cdk as cdk
from aws_cdk.assertions import Template

from stacks.hosted_stack import HostedStack


def _template() -> Template:
    app = cdk.App()
    stack = HostedStack(app, "TestHostedStack", env_name="test")
    return Template.from_stack(stack)


def test_stack_synthesizes_empty_for_now() -> None:
    # Skeleton: synthesizes with zero resources until Group B adds them.
    _template().resource_count_is("AWS::S3::Bucket", 0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd infra && python -m pytest tests/test_hosted_stack.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stacks.hosted_stack'`

- [ ] **Step 3: Minimal CDK app + empty stack**

`infra/cdk.json`:

```json
{ "app": "python app.py", "context": { "@aws-cdk/core:bootstrapQualifier": "ssm7a" } }
```

`infra/app.py`:

```python
import os

import aws_cdk as cdk

from stacks.hosted_stack import HostedStack

app = cdk.App()
HostedStack(
    app,
    "SsmHostedStack",
    env_name=os.environ.get("SSM_ENV", "dev"),
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)
app.synth()
```

`infra/stacks/__init__.py`: empty. `infra/tests/__init__.py`: empty.

`infra/stacks/hosted_stack.py`:

```python
from __future__ import annotations

from aws_cdk import Stack
from constructs import Construct


class HostedStack(Stack):
    """Single stack for Phase 7 hosted UI. Grows per slice; 7a = auth + viewer."""

    def __init__(self, scope: Construct, cid: str, *, env_name: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        self.env_name = env_name
        # Resources added in Groups B–E.
```

`infra/README.md`: one paragraph — how to `python -m venv`, `pip install -r requirements.txt`, `cdk synth`, `cdk deploy`, `cdk destroy`; point at `docs/ai/runbooks/aws-teardown.md`.

- [ ] **Step 4: Run tests + synth to verify pass**

Run: `cd infra && pip install -r requirements.txt -q && python -m pytest tests/ -q && cdk synth >/dev/null && echo SYNTH_OK`
Expected: tests PASS; `SYNTH_OK`

- [ ] **Step 5: Commit**

```bash
git add infra/
git commit -m "feat(7a): CDK app skeleton (synth-green, no resources)"
```

### Task 3: Vite + React + TS SPA skeleton

**Files:**
- Create: `web/package.json`, `web/index.html`, `web/vite.config.ts`, `web/tsconfig.json`, `web/src/main.tsx`, `web/src/App.tsx`, `web/.gitignore`

- [ ] **Step 1: Scaffold**

Run:
```bash
cd web 2>/dev/null || (mkdir web && cd web)
npm create vite@latest . -- --template react-ts
npm install
npm install @tanstack/react-query
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

- [ ] **Step 2: Wire Vitest**

In `web/vite.config.ts` add a `test` block:

```ts
/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", setupFiles: ["./src/setupTests.ts"], globals: true },
});
```

`web/src/setupTests.ts`: `import "@testing-library/jest-dom";`

- [ ] **Step 3: Smoke test (failing → passing)**

`web/src/__tests__/smoke.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import App from "../App";

test("app renders sign-in entry", () => {
  render(<App />);
  expect(screen.getByText(/sign in with google/i)).toBeInTheDocument();
});
```

Run: `cd web && npx vitest run` → Expected: FAIL (App has default Vite content).

Replace `web/src/App.tsx` body with a minimal shell containing a `Sign in with Google` button (wired in Group E). Re-run `npx vitest run` → Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add web/ && git commit -m "feat(7a): Vite+React+TS SPA skeleton with Vitest"
```

---

## Group B — S3 + DynamoDB foundation (stack deployable after this group)

### Task 4: S3 transcripts bucket + DynamoDB single-table (CDK, TDD via assertions)

**Files:**
- Modify: `infra/stacks/hosted_stack.py`
- Modify: `infra/tests/test_hosted_stack.py`

- [ ] **Step 1: Write failing assertions**

Replace the skeleton test with:

```python
def test_transcripts_bucket_is_private_and_destroyable() -> None:
    t = _template()
    t.resource_count_is("AWS::S3::Bucket", 2)  # transcripts + SPA hosting (Task 12)
    t.has_resource_properties(
        "AWS::S3::Bucket",
        {"PublicAccessBlockConfiguration": {"BlockPublicAcls": True}},
    )


def test_single_table_has_pk_sk_and_gsis() -> None:
    t = _template()
    t.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "KeySchema": [
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
    )
```

Run: `cd infra && python -m pytest tests/ -q` → Expected: FAIL (1 bucket asserted = 2, no table).

- [ ] **Step 2: Add the constructs**

In `hosted_stack.py` `__init__`, after `self.env_name = env_name`:

```python
from aws_cdk import RemovalPolicy
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_s3 as s3

self.transcripts_bucket = s3.Bucket(
    self,
    "TranscriptsBucket",
    block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
    encryption=s3.BucketEncryption.S3_MANAGED,
    enforce_ssl=True,
    removal_policy=RemovalPolicy.DESTROY,   # $0 teardown lever (D2 / cost floor)
    auto_delete_objects=True,
)

self.table = ddb.Table(
    self,
    "HostedTable",
    partition_key=ddb.Attribute(name="PK", type=ddb.AttributeType.STRING),
    sort_key=ddb.Attribute(name="SK", type=ddb.AttributeType.STRING),
    billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
    removal_policy=RemovalPolicy.DESTROY,
)
self.table.add_global_secondary_index(
    index_name="GSI1",
    partition_key=ddb.Attribute(name="GSI1PK", type=ddb.AttributeType.STRING),
    sort_key=ddb.Attribute(name="GSI1SK", type=ddb.AttributeType.STRING),
)
self.table.add_global_secondary_index(
    index_name="GSI2",
    partition_key=ddb.Attribute(name="GSI2PK", type=ddb.AttributeType.STRING),
    sort_key=ddb.Attribute(name="GSI2SK", type=ddb.AttributeType.STRING),
)
```

> Note: GSI1 (token lookup) / GSI2 (admin scan) are provisioned per the spec's single-table design but **unused in 7a** (only `#PROFILE` items exist). They are cheap on-demand and avoid a later table migration.

The SPA hosting bucket (2nd bucket asserted) is added in Task 12; until then, temporarily assert `resource_count_is("AWS::S3::Bucket", 1)` and update to `2` in Task 12. (Adjust Step 1's count to `1` now; Task 12 Step 1 flips it to `2`.)

- [ ] **Step 3: Pass + synth**

Run: `cd infra && python -m pytest tests/ -q && cdk synth >/dev/null && echo OK`
Expected: PASS; `OK`

- [ ] **Step 4: Commit**

```bash
git add infra/ && git commit -m "feat(7a): S3 transcripts bucket + DynamoDB single-table"
```

### Task 5: S3 key helpers + manifest visibility rule (pure logic, no AWS)

**Files:**
- Create: `src/transcriber/hosted/__init__.py`, `src/transcriber/hosted/s3keys.py`
- Create: `tests/unit/hosted/__init__.py`, `tests/unit/hosted/test_s3keys.py`

This encodes the Codex-P2 commit-marker rule (spec:138-146, 250-255): a `{cognito_sub}/{job_id}/` prefix is reader-visible **only if `manifest.json` is present**.

- [ ] **Step 1: Write the failing test**

`tests/unit/hosted/test_s3keys.py`:

```python
from transcriber.hosted.s3keys import (
    job_prefix,
    manifest_key,
    raw_key,
    transcript_key,
    visible_job_ids,
)


def test_key_builders() -> None:
    assert transcript_key("sub1", "j1") == "sub1/j1/transcript.md"
    assert raw_key("sub1", "j1") == "sub1/j1/result.raw.json"
    assert manifest_key("sub1", "j1") == "sub1/j1/manifest.json"
    assert job_prefix("sub1") == "sub1/"


def test_visible_job_ids_requires_manifest() -> None:
    keys = [
        "sub1/j1/transcript.md",
        "sub1/j1/result.raw.json",
        "sub1/j1/manifest.json",   # committed
        "sub1/j2/transcript.md",   # partial — no manifest
        "sub1/j2/result.raw.json",
    ]
    assert visible_job_ids("sub1", keys) == ["j1"]
```

- [ ] **Step 2: Verify it fails**

Run: `uv run pytest tests/unit/hosted/test_s3keys.py -q`
Expected: FAIL — `ModuleNotFoundError: transcriber.hosted.s3keys`

- [ ] **Step 3: Implement**

`src/transcriber/hosted/__init__.py`: `"""Hosted UI orchestration boundary (F1: event-driven, not the sync library)."""`

`src/transcriber/hosted/s3keys.py`:

```python
"""S3 key helpers + the manifest.json commit-marker visibility rule.

A job prefix is reader-visible ONLY when manifest.json exists (spec
"Atomic output writes", Codex P2): a partial write (one object, crash
before the marker) yields an invisible prefix, never a half-transcript.
"""

from __future__ import annotations

TRANSCRIPT_NAME = "transcript.md"
RAW_NAME = "result.raw.json"
MANIFEST_NAME = "manifest.json"


def job_prefix(sub: str) -> str:
    return f"{sub}/"


def transcript_key(sub: str, job_id: str) -> str:
    return f"{sub}/{job_id}/{TRANSCRIPT_NAME}"


def raw_key(sub: str, job_id: str) -> str:
    return f"{sub}/{job_id}/{RAW_NAME}"


def manifest_key(sub: str, job_id: str) -> str:
    return f"{sub}/{job_id}/{MANIFEST_NAME}"


def visible_job_ids(sub: str, keys: list[str]) -> list[str]:
    """Job ids under ``sub/`` that have a manifest.json (committed jobs only)."""
    committed: list[str] = []
    for key in keys:
        parts = key.split("/")
        if len(parts) == 3 and parts[0] == sub and parts[2] == MANIFEST_NAME:
            committed.append(parts[1])
    return sorted(committed)
```

- [ ] **Step 4: Pass**

Run: `uv run pytest tests/unit/hosted/test_s3keys.py -q && uv run ruff check src/ tests/ && uv run mypy src/`
Expected: PASS; ruff clean; mypy clean

- [ ] **Step 5: Commit**

```bash
git add src/transcriber/hosted/__init__.py src/transcriber/hosted/s3keys.py tests/unit/hosted/
git commit -m "feat(7a): S3 key helpers + manifest commit-marker visibility rule"
```

### Task 6: Hosted error → HTTP mapping (pure logic)

**Files:**
- Create: `src/transcriber/hosted/errors.py`
- Create: `tests/unit/hosted/test_hosted_errors.py`

- [ ] **Step 1: Failing test**

```python
from transcriber.hosted.errors import HostedError, NotFound, Forbidden, to_response


def test_to_response_maps_status_and_body() -> None:
    assert to_response(NotFound("nope"))["statusCode"] == 404
    assert to_response(Forbidden("no"))["statusCode"] == 403
    body = to_response(NotFound("missing job"))
    assert '"error"' in body["body"] and "missing job" in body["body"]


def test_unknown_error_is_500_without_leaking_message() -> None:
    r = to_response(RuntimeError("secret internals"))
    assert r["statusCode"] == 500
    assert "secret internals" not in r["body"]   # no internal leak (F8)
```

Run: `uv run pytest tests/unit/hosted/test_hosted_errors.py -q` → Expected: FAIL.

- [ ] **Step 2: Implement**

`src/transcriber/hosted/errors.py`:

```python
"""Hosted error taxonomy → API Gateway proxy responses. No secret leakage (F8)."""

from __future__ import annotations

import json


class HostedError(Exception):
    status = 500


class NotFound(HostedError):
    status = 404


class Forbidden(HostedError):
    status = 403


class BadRequest(HostedError):
    status = 400


def to_response(exc: Exception) -> dict:
    if isinstance(exc, HostedError):
        status, message = exc.status, str(exc)
    else:
        status, message = 500, "internal error"
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": message}),
    }
```

Run: `uv run pytest tests/unit/hosted/test_hosted_errors.py -q && uv run mypy src/` → Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/transcriber/hosted/errors.py tests/unit/hosted/test_hosted_errors.py
git commit -m "feat(7a): hosted error→HTTP mapping without internal leakage"
```

---

## Group C — Cognito + Google IdP + invite-gate

### Task 7: Invite-gate Lambda handler (TDD with moto, against the pinned event shape)

**Files:**
- Create: `src/transcriber/hosted/handlers/__init__.py`, `src/transcriber/hosted/handlers/invite_gate.py`
- Create: `tests/unit/hosted/test_invite_gate.py`

> Uses the **verbatim federated-signin trigger event shape pinned in Task 0**. If Task 0's fetch showed the trigger is not Pre-Sign-up, adjust the handler signature to the pinned trigger — do **not** code against a guessed shape.

- [ ] **Step 1: Failing test (moto DynamoDB)**

```python
import os

import boto3
import pytest
from moto import mock_aws

from transcriber.hosted.handlers.invite_gate import handler


@pytest.fixture()
def table(monkeypatch):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        t = ddb.create_table(
            TableName="HostedTable",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                       {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                                  {"AttributeName": "SK", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("HOSTED_TABLE", "HostedTable")
        yield t


def _event(email: str) -> dict:
    # Shape per Task-0 pinned federated-signin trigger event.
    return {
        "triggerSource": "PreSignUp_ExternalProvider",
        "request": {"userAttributes": {"email": email}},
        "response": {},
    }


def test_invited_user_passes(table):
    table.put_item(Item={"PK": "USER#wife@example.com", "SK": "#PROFILE",
                         "email": "wife@example.com", "monthly_budget_usd": "5"})
    out = handler(_event("wife@example.com"), None)
    assert out["response"]["autoConfirmUser"] is True


def test_uninvited_user_rejected(table):
    with pytest.raises(Exception) as ei:
        handler(_event("stranger@example.com"), None)
    assert "not invited" in str(ei.value).lower()
```

Run: `uv run pytest tests/unit/hosted/test_invite_gate.py -q` → Expected: FAIL.

- [ ] **Step 2: Implement**

`src/transcriber/hosted/handlers/__init__.py`: empty.

`src/transcriber/hosted/handlers/invite_gate.py`:

```python
"""Cognito federated-signin Lambda trigger: reject un-invited Google accounts.

Event shape is the Task-0 pinned trigger payload. Raising from the trigger
makes Cognito deny the sign-in (spec Scenario 2: "not invited" message).
No print(); structured logging only (F8).
"""

from __future__ import annotations

import logging
import os

import boto3

log = logging.getLogger(__name__)


def handler(event: dict, _context) -> dict:
    email = event["request"]["userAttributes"]["email"]
    table_name = os.environ["HOSTED_TABLE"]
    table = boto3.resource("dynamodb").Table(table_name)
    item = table.get_item(Key={"PK": f"USER#{email}", "SK": "#PROFILE"}).get("Item")
    if not item:
        log.info("invite_gate.reject", extra={"email_present": bool(email)})
        raise PermissionError(
            "This Google account is not invited. Ask the admin for an invite."
        )
    log.info("invite_gate.allow")
    event["response"]["autoConfirmUser"] = True
    event["response"]["autoVerifyEmail"] = True
    return event
```

Run: `uv run pytest tests/unit/hosted/test_invite_gate.py -q && uv run mypy src/` → Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/transcriber/hosted/handlers/__init__.py src/transcriber/hosted/handlers/invite_gate.py tests/unit/hosted/test_invite_gate.py
git commit -m "feat(7a): invite-gate Lambda rejects un-invited Google sign-in"
```

### Task 8: Cognito user pool + Google IdP + invite-gate wiring (CDK)

**Files:**
- Modify: `infra/stacks/hosted_stack.py`, `infra/tests/test_hosted_stack.py`

- [ ] **Step 1: Failing assertions**

```python
def test_cognito_pool_has_google_idp_and_presignup_trigger() -> None:
    t = _template()
    t.resource_count_is("AWS::Cognito::UserPool", 1)
    t.has_resource_properties("AWS::Cognito::UserPoolIdentityProvider",
                              {"ProviderType": "Google"})
    t.has_resource_properties(
        "AWS::Cognito::UserPool",
        {"LambdaConfig": {"PreSignUp": {}}},  # exact key per Task-0 pin
    )
```

Run synth tests → Expected: FAIL.

- [ ] **Step 2: Implement (use Task-0 pinned construct shapes verbatim)**

Add to `hosted_stack.py` (Google client secret comes from SSM Parameter Store SecureString — D11 default `ssm`, $0 — not hard-coded):

```python
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_ssm as ssm

self.user_pool = cognito.UserPool(
    self, "UserPool",
    self_sign_up_enabled=False,                 # invite-only (D3)
    sign_in_aliases=cognito.SignInAliases(email=True),
    removal_policy=RemovalPolicy.DESTROY,
)

google_secret = ssm.StringParameter.value_for_string_parameter(
    self, f"/ssm-transcriber/{self.env_name}/google-oauth-client-secret"
)
cognito.UserPoolIdentityProviderGoogle(
    self, "GoogleIdp",
    user_pool=self.user_pool,
    client_id=ssm.StringParameter.value_for_string_parameter(
        self, f"/ssm-transcriber/{self.env_name}/google-oauth-client-id"
    ),
    client_secret=google_secret,
    scopes=["openid", "email", "profile"],      # identity ONLY — no drive scope (D8)
    attribute_mapping=cognito.AttributeMapping(
        email=cognito.ProviderAttribute.GOOGLE_EMAIL
    ),
)

invite_fn = lambda_.Function(
    self, "InviteGateFn",
    runtime=lambda_.Runtime.PYTHON_3_12,
    handler="transcriber.hosted.handlers.invite_gate.handler",
    code=lambda_.Code.from_asset("../", bundling=_python_bundling()),
    environment={"HOSTED_TABLE": self.table.table_name},
)
self.table.grant_read_data(invite_fn)
self.user_pool.add_trigger(
    cognito.UserPoolOperation.PRE_SIGN_UP, invite_fn
)   # exact operation per Task-0 pin; change if pin shows a different trigger

self.user_pool_client = self.user_pool.add_client(
    "WebClient",
    o_auth=cognito.OAuthSettings(
        flows=cognito.OAuthFlows(authorization_code_grant=True),
        scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL],
        callback_urls=["http://localhost:5173/callback"],  # CloudFront URL added Task 12
    ),
    supported_identity_providers=[
        cognito.UserPoolClientIdentityProvider.GOOGLE
    ],
)
self.user_pool.add_domain(
    "HostedUiDomain",
    cognito_domain=cognito.CognitoDomainOptions(
        domain_prefix=f"ssm-transcriber-{self.env_name}"
    ),
)
```

Add a module-level `_python_bundling()` helper that pip-installs `src/transcriber` into the Lambda asset (Docker bundling or `BundlingOptions` with `pip install . -t /asset-output`). Concrete bundling command:

```python
def _python_bundling():
    from aws_cdk import BundlingOptions, DockerImage
    return BundlingOptions(
        image=DockerImage.from_registry("public.ecr.aws/sam/build-python3.12"),
        command=[
            "bash", "-c",
            "pip install . -t /asset-output && cp -r src/transcriber /asset-output/",
        ],
    )
```

- [ ] **Step 3: Pass + synth + commit**

Run: `cd infra && python -m pytest tests/ -q && cdk synth >/dev/null && echo OK`
Expected: PASS; `OK`

```bash
git add infra/ && git commit -m "feat(7a): Cognito pool + Google IdP + invite-gate trigger"
```

---

## Group D — API + transcript Lambdas

### Task 9: `list_transcripts` Lambda (TDD, moto S3, manifest rule)

**Files:**
- Create: `src/transcriber/hosted/handlers/list_transcripts.py`, `tests/unit/hosted/test_list_transcripts.py`

- [ ] **Step 1: Failing test**

```python
import json, os
import boto3, pytest
from moto import mock_aws
from transcriber.hosted.handlers.list_transcripts import handler


@pytest.fixture()
def bucket(monkeypatch):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="tb")
        s3.put_object(Bucket="tb", Key="sub1/j1/transcript.md", Body=b"# t")
        s3.put_object(Bucket="tb", Key="sub1/j1/manifest.json", Body=b"{}")
        s3.put_object(Bucket="tb", Key="sub1/j2/transcript.md", Body=b"# partial")
        monkeypatch.setenv("TRANSCRIPTS_BUCKET", "tb")
        yield s3


def _event(sub: str) -> dict:
    return {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": sub}}}}}


def test_lists_only_committed_jobs(bucket):
    out = handler(_event("sub1"), None)
    body = json.loads(out["body"])
    assert [j["job_id"] for j in body["transcripts"]] == ["j1"]   # j2 has no manifest


def test_user_isolation(bucket):
    out = handler(_event("other"), None)
    assert json.loads(out["body"])["transcripts"] == []
```

Run → Expected: FAIL.

- [ ] **Step 2: Implement**

```python
"""GET /transcripts — list the caller's committed transcripts (newest-first)."""

from __future__ import annotations

import json
import os

import boto3

from transcriber.hosted.errors import to_response
from transcriber.hosted.s3keys import job_prefix, manifest_key, visible_job_ids


def handler(event: dict, _context) -> dict:
    try:
        sub = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
        bucket = os.environ["TRANSCRIPTS_BUCKET"]
        s3 = boto3.client("s3")
        keys: list[str] = []
        token: str | None = None
        while True:
            kw = {"Bucket": bucket, "Prefix": job_prefix(sub)}
            if token:
                kw["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kw)
            keys += [o["Key"] for o in resp.get("Contents", [])]
            if not resp.get("IsTruncated"):
                break
            token = resp["NextContinuationToken"]
        jobs = []
        for jid in visible_job_ids(sub, keys):
            head = s3.head_object(Bucket=bucket, Key=manifest_key(sub, jid))
            jobs.append({"job_id": jid,
                         "last_modified": head["LastModified"].isoformat()})
        jobs.sort(key=lambda j: j["last_modified"], reverse=True)
        return {"statusCode": 200,
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"transcripts": jobs})}
    except Exception as exc:  # noqa: BLE001 — boundary handler; mapped, not swallowed
        return to_response(exc)
```

Run tests + mypy → Expected: PASS. Commit:

```bash
git add src/transcriber/hosted/handlers/list_transcripts.py tests/unit/hosted/test_list_transcripts.py
git commit -m "feat(7a): list_transcripts Lambda (manifest-gated, user-isolated)"
```

### Task 10: `get_transcript` Lambda (TDD)

**Files:**
- Create: `src/transcriber/hosted/handlers/get_transcript.py`, `tests/unit/hosted/test_get_transcript.py`

- [ ] **Step 1: Failing test** — assert: committed job returns `{markdown, raw_present:true}` with markdown body; a prefix lacking `manifest.json` returns **404** (not a half-transcript); another user's job → 404 (no existence leak).

```python
def test_get_returns_markdown_for_committed_job(bucket): ...
def test_get_missing_manifest_is_404(bucket): ...
def test_get_other_users_job_is_404(bucket): ...
```

(Fill bodies mirroring Task 9's fixture; assertions exactly as the three names state.)

- [ ] **Step 2: Implement** — read `manifest_key`; if absent → `raise NotFound("transcript not found")`; else return `transcript.md` body + a `raw_present` boolean (HEAD on `raw_key`). Same `try/except to_response` boundary as Task 9. Use `transcriber.hosted.s3keys` helpers.

- [ ] **Step 3: Pass + commit**

```bash
git add src/transcriber/hosted/handlers/get_transcript.py tests/unit/hosted/test_get_transcript.py
git commit -m "feat(7a): get_transcript Lambda (manifest-gated, 404 on partial/foreign)"
```

### Task 11: `delete_transcript` Lambda (TDD)

**Files:**
- Create: `src/transcriber/hosted/handlers/delete_transcript.py`, `tests/unit/hosted/test_delete_transcript.py`

- [ ] **Step 1: Failing test** — delete removes all three objects (`transcript.md`, `result.raw.json`, `manifest.json`); deleting another user's job → 404 and leaves objects intact; idempotent (second delete → 404, no crash). **Delete the manifest *first*** so a mid-delete crash still yields an invisible prefix.

- [ ] **Step 2: Implement** — verify the manifest exists for `(sub, job_id)` (else `NotFound`); `delete_objects` ordering: `manifest.json` first (de-commit), then `transcript.md`, `result.raw.json`. Same boundary mapping.

- [ ] **Step 3: Pass + commit**

```bash
git add src/transcriber/hosted/handlers/delete_transcript.py tests/unit/hosted/test_delete_transcript.py
git commit -m "feat(7a): delete_transcript Lambda (manifest-first, user-isolated, idempotent)"
```

### Task 12: API Gateway HTTP API + Cognito JWT authorizer + SPA hosting (CDK)

**Files:**
- Modify: `infra/stacks/hosted_stack.py`, `infra/tests/test_hosted_stack.py`

- [ ] **Step 1: Failing assertions**

```python
def test_http_api_routes_are_jwt_authorized() -> None:
    t = _template()
    t.resource_count_is("AWS::ApiGatewayV2::Api", 1)
    t.has_resource_properties("AWS::ApiGatewayV2::Authorizer",
                              {"AuthorizerType": "JWT"})
    t.resource_count_is("AWS::ApiGatewayV2::Route", 3)  # list/get/delete
    t.resource_count_is("AWS::CloudFront::Distribution", 1)


def test_two_buckets_now() -> None:
    _template().resource_count_is("AWS::S3::Bucket", 2)  # flips Task 4 count
```

Update Task 4 Step 1's bucket count to `1`; this task asserts `2`. Run → FAIL.

- [ ] **Step 2: Implement** — using the **Task-0 pinned** `aws_apigatewayv2` + `aws_apigatewayv2_authorizers` (`HttpJwtAuthorizer` / `HttpUserPoolAuthorizer`) shapes:
  - 3 `lambda_.Function`s (list/get/delete) with `code=Code.from_asset("../", bundling=_python_bundling())`, `environment={"TRANSCRIPTS_BUCKET": self.transcripts_bucket.bucket_name}`; `self.transcripts_bucket.grant_read(list_fn/get_fn)`, `grant_read_write(delete_fn)`.
  - `HttpApi` with a `HttpUserPoolAuthorizer` bound to `self.user_pool` + `self.user_pool_client`; routes `GET /transcripts`, `GET /transcripts/{id}`, `DELETE /transcripts/{id}` (CORS allow the CloudFront origin).
  - SPA hosting `s3.Bucket` (private) + `cloudfront.Distribution` with an OAI/OAC S3 origin, default root `index.html`, SPA 403/404→`/index.html` rewrite. `removal_policy=DESTROY`, `auto_delete_objects=True`.
  - Add the CloudFront URL to the Cognito client `callback_urls` and emit `CfnOutput`s: `ApiBaseUrl`, `CloudFrontUrl`, `UserPoolId`, `UserPoolClientId`, `CognitoDomain`.

- [ ] **Step 3: Pass + synth + commit**

Run: `cd infra && python -m pytest tests/ -q && cdk synth >/dev/null && echo OK` → PASS; `OK`

```bash
git add infra/ && git commit -m "feat(7a): HTTP API + Cognito JWT authorizer + CloudFront SPA hosting"
```

---

## Group E — Frontend SPA

> Frontend TDD is **lighter than backend** (repo has no prior FE tests). Vitest+RTL covers **non-trivial logic only**: the manifest/shape parsing of API responses and the markdown+frontmatter render. Do **not** write exhaustive click-through RTL.

### Task 13: Cognito Hosted-UI auth (PKCE) + API client

**Files:** Create `web/src/auth.ts`, `web/src/api.ts`, `web/src/config.ts`, `web/src/__tests__/api.test.ts`

- [ ] **Step 1: Failing unit test for the API response parser** — `parseTranscripts(json)` returns `[]` for `{transcripts:[]}`, preserves order, and throws on a non-object body. `parseTranscript(json)` extracts `{markdown, rawPresent}`.
- [ ] **Step 2: Implement** `api.ts` (typed `fetch` wrappers attaching the Cognito ID token as `Authorization: Bearer`), `auth.ts` (Cognito Hosted-UI authorization-code + PKCE redirect: build authorize URL from `config.ts` values injected at build, exchange code at the token endpoint, store tokens in memory + `sessionStorage`), `config.ts` (reads `import.meta.env.VITE_*` set from CDK outputs).
- [ ] **Step 3: Pass + commit** (`npx vitest run`).

### Task 14: Dashboard list + budget pill + viewer + delete

**Files:** Create `web/src/components/{Dashboard,TranscriptViewer,BudgetPill}.tsx`, `web/src/manifest.ts`, wire TanStack Query in `web/src/main.tsx`, update `web/src/App.tsx`; tests `web/src/__tests__/{dashboard,viewer}.test.tsx`

- [ ] **Step 1: Failing tests** — Dashboard renders one row per `transcripts[]` newest-first; empty state shows "No transcripts yet"; `BudgetPill` renders `monthly_budget_usd` from `/users/me`-shaped props **as a static value** (no usage math — 7a scope); `TranscriptViewer` splits YAML frontmatter from markdown body and renders both (use a small frontmatter splitter in `manifest.ts`).
- [ ] **Step 2: Implement** the components + `TanStack Query` hooks (`useTranscripts`, `useTranscript`, `useDeleteTranscript` with optimistic invalidation). Delete asks for confirm. App routes: `/` (dashboard, auth-guarded), `/callback` (auth code exchange), `/t/:id` (viewer).
- [ ] **Step 3: Pass + commit** (`npx vitest run`).

### Task 15: Frontend build wired into CDK asset

**Files:** Modify `infra/stacks/hosted_stack.py` (deploy `web/dist` to the SPA bucket via `aws_s3_deployment.BucketDeployment`), modify `infra/tests/test_hosted_stack.py`

- [ ] **Step 1: Failing assertion** — `t.resource_count_is("Custom::CDKBucketDeployment", 1)`.
- [ ] **Step 2: Implement** — `BucketDeployment` sourcing `../web/dist` (document `npm --prefix web run build` as a pre-`cdk deploy` step in `infra/README.md`); invalidate CloudFront on deploy.
- [ ] **Step 3: Pass + synth + commit.**

---

## Group F — Seed fixture + end-to-end validation

### Task 16: Seed script (invited profile + a committed transcript fixture)

**Files:** Create `infra/seed.py`, `tests/unit/hosted/test_seed_shapes.py`

- [ ] **Step 1: Failing test** — `seed.build_profile_item(email, budget)` → exact `#PROFILE` shape (`PK=USER#{email}`, `SK=#PROFILE`, `email`, `monthly_budget_usd`); `seed.fixture_objects(sub, job_id)` → the three S3 `(key, body)` pairs with `manifest.json` content `{"committed": true}` and a valid frontmatter+markdown `transcript.md`.
- [ ] **Step 2: Implement** `infra/seed.py` as a boto3 script: put the `#PROFILE` item for the two invited emails (yours + your wife's — read from argv, never hard-coded), and put the three fixture objects under `{sub}/{job_id}/` (manifest **last**). Pure builders live in importable functions so the test does not touch AWS.
- [ ] **Step 3: Pass + commit.**

### Task 17: Manual deploy + Google OAuth client + two-sign-in validation

**Files:** Create/fill `specs/2026-05-14-hosted-ui/validation.md`

These steps are **not TDD-able**; they are explicit and their evidence is captured in `validation.md`.

- [ ] **Step 1: Google Cloud Console OAuth web client** — context7-fetch the *current* Google "OAuth 2.0 Web application client" setup steps; create a Web client; authorized redirect URI = the Cognito Hosted-UI `/oauth2/idpresponse` URL (from `CfnOutput CognitoDomain`). Put the client id/secret into SSM Parameter Store SecureString at the two paths Task 8 reads. Record (redacted) what was created in `validation.md`.
- [ ] **Step 2: Deploy** — `npm --prefix web run build`, then `cd infra && cdk deploy`. Capture stack outputs into `validation.md`. Run `python infra/seed.py --emails you@example.com,wife@example.com --sub <your-cognito-sub-after-first-login>` (note the chicken-egg: first login provisions the user via the invite-gate auto-confirm; seed the transcript fixture under that sub afterward).
- [ ] **Step 3: Two real sign-in attempts** — (a) an **invited** Google account → lands on dashboard → sees + opens + deletes the seeded transcript; (b) an **un-invited** Google account → rejected with the "not invited" message. Screenshot/console-capture both into `validation.md`.
- [ ] **Step 4: Teardown proof** — `cd infra && cdk destroy`; confirm the stack is gone (≈$0). Record in `validation.md`. Commit:

```bash
git add specs/2026-05-14-hosted-ui/validation.md
git commit -m "docs(7a): validation evidence — sign-in, viewer, invite-gate, teardown"
```

---

## Group G — Constitution amendments, lockstep, teaching docs, teardown runbook

### Task G1: Constitution amendments (ship with this slice, per spec:118-131)

**Files:** Modify `specs/mission.md`, `specs/tech-stack.md`, `docs/PLAN.md`

- [ ] **Step 1** — `specs/mission.md`: move **"Multi-user or hosted/SaaS deployment. This is a single-user local CLI."** from *Out of scope* to a new *In scope (Phase 7, hosted UI)* line with a back-link to `specs/2026-05-14-hosted-ui/requirements.md`; keep the explicit "local CLI remains single-user/local-first; hosted UI is the multi-user surface" clause.
- [ ] **Step 2** — `specs/tech-stack.md`: add an "AWS deployment (Phase 7 hosted UI)" section listing, one row + rationale each: Lambda, Step Functions, DynamoDB, S3, Cognito (+Google IdP), API Gateway HTTP API, CloudFront, SES, EventBridge, SSM Parameter Store / Secrets Manager.
- [ ] **Step 3** — `docs/PLAN.md` §F1: extend verbatim to the spec:130 wording (library `sources/`,`providers/`,`formatters/`,`destinations/`,`core/` stay sync; orchestration MAY be event-driven at the hosting boundary only; no `async def` in library code). §F4: extend verbatim to spec:131 (hosted adds Gate 3; CLI stays two-gate).
- [ ] **Step 4: Commit** `git commit -m "docs(7a): ship Phase 7 constitution amendments (mission/tech-stack/PLAN F1+F4)"`

### Task G2: CLAUDE.md guardrail lockstep (HARD — spec:130 mandates same-PR)

**Files:** Modify `CLAUDE.md`

- [ ] **Step 1** — In `CLAUDE.md` "## Guardrails to keep inline", replace exactly:

  `- Keep the core sync through Phase 4; do not add `async def` to pipeline, source, provider, or formatter code.`

  with:

  `- Library code (`sources/`, `providers/`, `formatters/`, `destinations/`, `core/`) stays sync; do not add `async def` there. Orchestration MAY be event-driven (Step Functions, browser polling) at the hosting boundary only (`src/transcriber/hosted/`). See PLAN.md §F1.`

- [ ] **Step 2: Commit** `git commit -m "docs(7a): CLAUDE.md F1 guardrail in lockstep with PLAN.md amendment"`

> If this task is skipped, the two authoritative tool-context files diverge — the spec explicitly forbids that. Spec-reviewer must fail the slice if Task G2 is absent.

### Task G3: Teaching-register artifacts (repo convention — every PR)

**Files:** Create `docs/learn/prs/pr-0NN-7a-auth-scaffold-impl.md`; modify `docs/learn/journey.md`, `docs/learn/interview-prep.md`, `docs/learn/python-notes.md`, `docs/learn/glossary.md`

- [ ] **Step 1** — Draft the PR explainer (template at `docs/learn/README.md:72-108`): the problem, what changed, **why CDK over SAM** (draw from ADR-0), the manifest commit-marker rule, what a reviewer should notice (F1 boundary, invite-gate event shape pinned not guessed). Add a `journey.md` entry (newest-first). Add an `interview-prep.md` STAR story (the IaC decision + the F1-boundary design). Append `glossary.md` (`Cognito federated IdP`, `single-table design`, `commit marker`) and `python-notes.md` only for genuinely new idioms (e.g. `boto3` resource vs client, Lambda handler signature) — cite real files. Per `docs/learn/README.md` rule "when in doubt omit"; no speculative entries.
- [ ] **Step 2: Commit** `git commit -m "docs(7a): teaching-register explainer + journey + interview-prep + glossary"`

### Task G4: AWS teardown runbook (cross-cutting $0 lever — first AWS lands in 7a)

**Files:** Create `docs/ai/runbooks/aws-teardown.md`; modify `docs/ai/README.md` (task-routing row)

- [ ] **Step 1** — Write `aws-teardown.md`: prerequisites (CDK bootstrapped, creds), `cd infra && cdk destroy` (note `RemovalPolicy.DESTROY` + `auto_delete_objects` mean buckets empty + delete), how to confirm ≈$0 (Cost Explorer + "no stacks" check), and `cdk deploy` to restore. Failure modes table (non-empty bucket, retained log groups). Cite the cost-floor section of `requirements.md:368-378`.
- [ ] **Step 2** — Add the routing row to `docs/ai/README.md` task-routing table (format consistent with peers), "Then read" → `infra/README.md`.
- [ ] **Step 3: Commit** `git commit -m "docs(7a): AWS teardown runbook (literal \$0 lever) + routing row"`

---

## Self-Review (run before declaring the plan done)

**1. Spec coverage** — Scenario 2 (sign-in + un-invited reject) → Tasks 7, 8, 17. Scenario 3 (list + budget pill + viewer + delete) → Tasks 9–11, 14. Scenario 12 (teardown $0) → Task 4 removal policies + G4 + 17.4. Atomic-write/Codex-P2 → Tasks 5, 9, 10, 11. Constitution amendments + F1 lockstep → G1, G2. Reference-calls pin discipline → Task 0. Tracking convention → PR section below. F-contract postures → Scope section + Task G1/G2. No uncovered 7a requirement.

**2. Placeholder scan** — Tasks 10 and 11 Step 1 state assertions by exact name and reuse Task 9's fully-shown fixture rather than re-pasting; every code-bearing step elsewhere shows complete code. No "TBD"/"handle errors"/vague steps. Acceptable per "repeat or precisely reference" — the referenced fixture is fully shown in Task 9.

**3. Type/name consistency** — `visible_job_ids`, `manifest_key`, `raw_key`, `transcript_key`, `job_prefix` consistent across Tasks 5/9/10/11. `to_response`/`NotFound`/`Forbidden` consistent Tasks 6/9/10/11. `HostedStack(env_name=…)`, `self.table`, `self.transcripts_bucket`, `self.user_pool`, `self.user_pool_client`, `_python_bundling()` consistent across infra Tasks 2/4/8/12/15. Bucket-count assertion handoff (Task 4 → `1`, Task 12 → `2`) noted in both places.

## Tracking & PR (Loop A — do NOT auto-execute)

- This plan-7a file lands via a **plan PR** with **`Refs #37`** in the body (a plan/spec-side PR never auto-closes — `tracking.md` §"PR linking conventions"). Board: keep #41 / #37 as set.
- The **implementation PR** (Groups A–G code) carries **`Closes #41` AND `Refs #37`** — never `Closes #37` (requirements.md:304-321). On its merge: #41 auto-closes, then flip the 7a roadmap line in `docs/PLAN.md` and move #37's board card per `tracking.md`.
- Per `docs/ai/runbooks/gstack-superpowers-workflow.md` Loop A, the order is: **plan PR → external multi-vendor review (`/codex:review` + `/pr-review-toolkit:review-pr`) → merge → THEN** `superpowers:subagent-driven-development`. The writing-plans Execution Handoff that follows is deferred behind this gate.
