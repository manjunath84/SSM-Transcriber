# AWS Teardown Runbook

AI-agnostic guide to tear down the Phase 7 hosted AWS stack and restore it.
This is the **literal-$0 lever** for long dormancy — the spec's primary
cost-control mechanism when the UI is not in use.

## Purpose

The hosted stack (Lambda, Cognito, API Gateway, DynamoDB, S3, CloudFront,
CloudWatch Logs) incurs a non-zero monthly floor even when idle:

- S3 storage: pennies (text durable; audio auto-deleted 14d).
- Route 53: ~$0.50/mo **only if** a custom domain is attached. v1 default:
  CloudFront default domain = $0.
- CloudWatch Logs: ≈free at this volume with 14-day retention.
- Cognito: free tier 50k MAU → $0.
- Secrets backend: SSM Parameter Store SecureString = $0 (the default);
  Secrets Manager ≈$0.80/mo for 2 secrets (opt-in, operator-provisioned).

**Realistic idle floor:** ≈$0 with SSM Parameter Store (no Secrets Manager).

To achieve **literal $0 during dormancy**, tear down the entire CloudFormation
stack: `cdk destroy` empties and removes all S3 buckets, DynamoDB tables,
Lambda functions, API Gateway, Cognito user pool, and CloudWatch log groups.
Operator-provisioned items (SSM Parameter Store client-id param, Secrets
Manager secret if used — not created by the stack) remain and must be deleted
separately if total $0 is required.

See **Cost floor** in
[`specs/2026-05-14-hosted-ui/requirements.md`](../../specs/2026-05-14-hosted-ui/requirements.md)
(~lines 668–678) for the detailed breakdown.

## Prerequisites (check, don't assume)

- **AWS credentials configured.** Verify `aws sts get-caller-identity` returns
  a valid account/ARN.
- **CDK bootstrapped in the target AWS account/region.** If not, run `cd infra &&
  PATH=.venv/bin:$PATH npx --yes aws-cdk@2 bootstrap` once per
  account–region pair.
- **`infra/.venv` activated and synced.** The infra dir has its own
  `requirements.txt` and isolated venv (separate from the root uv project).
  ```bash
  cd infra
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  ```
  (`cdk.json` runs bare `python`, so the venv must be on `PATH` when you
  invoke CDK.)

## Teardown

Destroy all hosted AWS resources:

```bash
cd infra
source .venv/bin/activate  # Ensure the infra venv is active
PATH=.venv/bin:$PATH npx --yes aws-cdk@2 destroy
```

CDK will print the resources to be removed and prompt for confirmation. Review
the list and confirm.

**⚠️ WARNING — this is irreversible:**

The stack has `RemovalPolicy.DESTROY` + `auto_delete_objects=True` on both S3
buckets and the DynamoDB table. `cdk destroy` will:

1. **Empty** the S3 buckets (deletes all transcript audio files and text
   outputs).
2. **Delete** the buckets themselves.
3. **Delete** the DynamoDB table (all user profiles, transcription metadata,
   and chat history are **permanently removed**).
4. **Delete** Lambda functions, API Gateway endpoints, Cognito user pool,
   CloudWatch log groups, CloudFront distribution, and other stack resources.

**This is the intended dormancy behavior.** There is no restore from trash;
once the stack is destroyed, all data is gone unless it was backed up
separately (e.g., exports to Google Drive).

Operator-provisioned items (SSM Parameter Store `client_id` param, Secrets
Manager secret if configured for Google OAuth) are **NOT** created or managed
by the stack and will **NOT** be deleted by `cdk destroy`. To achieve literal
$0, delete them manually:

```bash
# Delete the client-id SSM Parameter
aws ssm delete-parameter --name /ssm-transcriber/<env>/google-oauth-client-id --region <region>

# Delete Secrets Manager secret (if provisioned — optional)
aws secretsmanager delete-secret \
  --secret-id ssm-transcriber/<env>/google-oauth-client-secret \
  --force-delete-without-recovery \
  --region <region>
```

Replace `<env>` with your deployment environment (e.g., `dev`, `prod`) and
`<region>` with the AWS region where these were created (e.g., `us-east-1`).

## Confirm ~$0

After teardown, verify that spend is effectively zero:

| Item | How to check |
|------|--------------|
| CloudFormation stack | `aws cloudformation describe-stacks --stack-name <StackName>` should return no results or `StackStatus: DELETE_COMPLETE`. The stack no longer appears in the AWS Console → CloudFormation. |
| S3 buckets | `aws s3 ls` should list no buckets created by the stack (bucket names typically contain the stack name or deployment hash). |
| DynamoDB table | `aws dynamodb list-tables --region <region>` should not include the transcriber table. |
| Cost Explorer | AWS Console → Billing → Cost Explorer shows no ongoing hosted (API, Lambda, DynamoDB) spend in the current and prior periods. Storage (S3 remaining text files if any) and Route 53 (if custom domain) will appear until those resources are also cleaned. |
| SSM Parameter + Secrets Manager | These appear as separate line items in Cost Explorer if not manually deleted (see Teardown above). |

## Redeploy / Restore

To bring the stack back online after dormancy:

```bash
cd infra
source .venv/bin/activate
npm --prefix ../web run build  # Must run from repo root (web/dist is needed at synth time)
PATH=.venv/bin:$PATH npx --yes aws-cdk@2 deploy
```

**⚠️ Docker is required for a real deploy.** The infra uses CDK asset bundling
to package Lambda code, which runs `pip install` inside a Docker container.
Start the Docker daemon before running `cdk deploy`. (Tests and shape-only
synth can skip Docker if `CDK_SKIP_BUNDLING=1` is set, but real deploys
cannot.)

CDK will synth the CloudFormation template, confirm the stack changes, and
deploy. On success, the hosted stack is live again. See
[`infra/README.md`](../../infra/README.md) for the full CDK invocation details
and prerequisites.

## Failure modes

| Symptom | Meaning | Recovery |
|---------|---------|----------|
| Stack deletion fails with `DELETE_FAILED` and resource in use | A resource is locked or referenced by another resource | Check CloudFormation events for the specific resource; manually release locks or dependencies, then re-run `cdk destroy`. |
| CloudWatch log groups remain after stack deletion | CloudFormation does not delete retained log groups by default; they linger and incur pennies of storage | Delete manually: `aws logs delete-log-group --log-group-name /aws/lambda/<FunctionName> --region <region>` for each function. |
| S3 bucket deletion fails with `bucket not empty` | `auto_delete_objects=True` did not empty the bucket (e.g., object lock or versioning interference) | Manually empty the bucket: `aws s3 rm s3://<BucketName> --recursive`, then re-run `cdk destroy`. |
| `cdk destroy` hangs or times out | CDK waiting for CloudFormation deletion; stack is very large or has dependencies | Let it continue (may take several minutes). If it truly hangs, you can cancel and monitor the stack deletion in the AWS Console. |
| Secrets Manager or SSM params were NOT deleted | `cdk destroy` does not manage operator-provisioned items | Delete them manually per the Teardown section above. Verify with `aws secretsmanager describe-secret` and `aws ssm describe-parameters --filters "Key=Name,Values=/ssm-transcriber/"`. |
| Docker daemon not running during `cdk deploy` | CDK bundling fails with `Cannot connect to the Docker daemon` | Start Docker, then re-run `cdk deploy`. For tests only, set `CDK_SKIP_BUNDLING=1`. |
| `web/dist` missing before `cdk deploy` | CDK asset synth fails; the frontend SPA is required at synth time | Run `npm --prefix web run build` from the repo root before `cdk deploy`. |

## Notes

- Runbook assumes `npx --yes aws-cdk@2` (no global `cdk` install). The infra
  venv must be on `PATH` so that `cdk.json`'s `"app": "python app.py"` can
  resolve `python` correctly.
- All commands are idempotent (safe to re-run). `cdk destroy` is safe to invoke
  on an already-destroyed stack.
- SSM Parameter Store / Secrets Manager are not Stack resources and are not
  visible to CloudFormation. Operator must provision and delete them
  separately. See the Teardown section for the commands.
