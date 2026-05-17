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
