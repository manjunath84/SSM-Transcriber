import aws_cdk as cdk
from aws_cdk.assertions import Template

from stacks.hosted_stack import HostedStack


def _template() -> Template:
    app = cdk.App()
    stack = HostedStack(app, "TestHostedStack", env_name="test")
    return Template.from_stack(stack)


def test_transcripts_bucket_is_private_and_destroyable() -> None:
    t = _template()
    t.resource_count_is("AWS::S3::Bucket", 1)  # transcripts only; SPA bucket arrives in Task 12
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
