# infra — AWS CDK v2 (Python)

Standalone AWS CDK v2 app for the Phase 7 hosted UI. It is **separate** from
the uv-managed core project: it has its own `requirements.txt` and its own
virtualenv, and CDK is intentionally **not** added to the root `pyproject.toml`.

Set up and operate it from inside this directory with an isolated venv, then
drive synth/deploy/destroy via the CDK CLI (invoked through `npx` so no global
install is required):

```bash
cd infra
python -m venv .venv && source .venv/bin/activate   # `python` must now resolve
pip install -r requirements.txt                     #   to this venv — cdk.json
python -m pytest tests/ -q                           #   runs `python app.py`
npx --yes aws-cdk@2 synth                            # synthesize CloudFormation
npx --yes aws-cdk@2 deploy                            # deploy (needs AWS creds)
npx --yes aws-cdk@2 destroy                           # tear everything down
```

`cdk.json` sets `"app": "python app.py"`, so the venv must be active (or
`python` otherwise pointed at it) when running any `cdk` command. To tear down
all hosted AWS resources and avoid lingering spend, follow
[`docs/ai/runbooks/aws-teardown.md`](../docs/ai/runbooks/aws-teardown.md).

## Frontend build is a prerequisite (`web/dist` must exist)

The stack ships the SPA via `aws_s3_deployment.BucketDeployment` sourcing
`../web/dist`. CDK resolves that asset **at synth time**, so the directory
must exist before *any* `cdk synth` / `cdk deploy` **and before the infra
test suite** (the assertion tests synth the stack). `web/dist` is a build
artifact (gitignored), so run the Vite build first, from the repo root:

```bash
npm --prefix web run build      # emits web/dist/ — required before cdk/tests
```

If `web/dist` is missing you'll see a synth-time asset error rather than a
clean test failure. (`Source.asset` on this prebuilt dir does **not**
Docker-bundle — see the Docker note below.)

### Runtime config (no `VITE_*` at build time)

The SPA's API/Cognito/CloudFront config values are this stack's CfnOutputs,
which only exist *after* `cdk deploy`. So `npm --prefix web run build` needs
**no environment variables** — do not pass `VITE_*`. Instead the stack writes
a `config.json` into the SPA bucket from its own deploy-resolved values: the
`SpaDeployment` `BucketDeployment` merges **two sources** — the `web/dist`
asset and a `Source.json_data("config.json", {...})` — into one deployment.
(One deployment, not two: a separate config-only deployment would be deleted
by the dist deployment's default `aws s3 sync --delete`, since `config.json`
is not in `web/dist`. Merging keeps the default prune — stale hashed Vite
assets are cleaned — without wiping `config.json`.) The SPA fetches
`/config.json` at runtime, falling back to `import.meta.env.VITE_*` only for
local `vite` dev. Flow: build the SPA (no env) → `cdk deploy` (writes dist +
`config.json`, invalidates CloudFront via `distribution_paths=["/*"]`). The
`ApiBaseUrl` / `CognitoDomain` / `UserPoolClientId` / `CloudFrontUrl`
CfnOutputs remain for operator/automation use.

## Docker is required only for real bundling (deploy), NOT for tests

Lambda code is packaged via CDK asset bundling
(`Code.from_asset(..., bundling=BundlingOptions(image=DockerImage...))`),
which runs `pip install` inside a `public.ecr.aws/sam/build-python3.12`
container. CDK runs this bundling **during synthesis**.

To keep the infra unit tests (and a shape-only `cdk synth`) runnable
**without Docker**, `_lambda_code()` honours `CDK_SKIP_BUNDLING=1`: when
set, it uses a plain unbundled asset. The `assertions.Template` suite
asserts resource *shapes* (Cognito / API routes / buckets), not Lambda
code content, so the stub asset is sufficient and correct for tests.
`infra/tests/test_hosted_stack.py` sets this var on import, so
`python -m pytest tests/` passes with no Docker daemon.

**Docker IS required for a real `cdk deploy`** (and any `cdk synth` you
want to produce a deployable artifact): leave `CDK_SKIP_BUNDLING` unset
so the real pip-bundled package is built. The user-run Task 17 deploy
requires Docker for this reason. If you run tests/synth without Docker
and without the skip var, you'll see `Cannot connect to the Docker
daemon` / `docker exited with status 125` — set `CDK_SKIP_BUNDLING=1`
(tests already do) or start Docker.
