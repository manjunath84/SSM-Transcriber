import os

# Infra assertion tests check resource SHAPES, not Lambda code content, so
# they must not require Docker for Lambda asset bundling. Set before the
# stack is imported/synthesized. Real `cdk synth`/`cdk deploy` is a separate
# process that does not import this module, so it still bundles for real.
os.environ.setdefault("CDK_SKIP_BUNDLING", "1")

import aws_cdk as cdk  # noqa: E402
from aws_cdk.assertions import Template  # noqa: E402

from stacks.hosted_stack import HostedStack  # noqa: E402


def _template() -> Template:
    app = cdk.App()
    stack = HostedStack(app, "TestHostedStack", env_name="test")
    return Template.from_stack(stack)


def test_transcripts_bucket_is_private_and_destroyable() -> None:
    t = _template()
    t.resource_count_is("AWS::S3::Bucket", 2)  # transcripts + SPA bucket (Task 12)
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


def test_cognito_pool_has_google_idp_and_presignup_trigger() -> None:
    t = _template()
    t.resource_count_is("AWS::Cognito::UserPool", 1)
    t.has_resource_properties("AWS::Cognito::UserPoolIdentityProvider",
                              {"ProviderType": "Google"})
    t.has_resource_properties(
        "AWS::Cognito::UserPool",
        {"LambdaConfig": {"PreSignUp": {}}},  # exact key per Task-0 pin
    )


def test_http_api_routes_are_jwt_authorized() -> None:
    t = _template()
    t.resource_count_is("AWS::ApiGatewayV2::Api", 1)
    t.has_resource_properties("AWS::ApiGatewayV2::Authorizer",
                              {"AuthorizerType": "JWT"})
    t.resource_count_is("AWS::ApiGatewayV2::Route", 4)  # list/get/delete + GET /users/me
    t.resource_count_is("AWS::CloudFront::Distribution", 1)


def test_two_buckets_now() -> None:
    _template().resource_count_is("AWS::S3::Bucket", 2)  # flips Task 4 count


def test_spa_bucket_deployment_present() -> None:
    _template().resource_count_is("Custom::CDKBucketDeployment", 1)
