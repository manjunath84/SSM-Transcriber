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
