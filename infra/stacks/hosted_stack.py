from __future__ import annotations

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ssm as ssm
from constructs import Construct


def _python_bundling():
    from aws_cdk import BundlingOptions, DockerImage
    return BundlingOptions(
        image=DockerImage.from_registry("public.ecr.aws/sam/build-python3.12"),
        command=["bash", "-c", "pip install . -t /asset-output"],
    )


def _lambda_code():
    return lambda_.Code.from_asset(
        "../",
        bundling=_python_bundling(),
        exclude=[
            "web", ".venv", ".git", "tests", "docs", "infra",
            "output", "temp", "**/__pycache__", "**/*.pyc",
        ],
    )


class HostedStack(Stack):
    """Single stack for Phase 7 hosted UI. Grows per slice; 7a = auth + viewer."""

    def __init__(self, scope: Construct, cid: str, *, env_name: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        self.env_name = env_name

        self.transcripts_bucket = s3.Bucket(
            self,
            "TranscriptsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,  # $0 teardown lever (D2 / cost floor)
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
        self.user_pool = cognito.UserPool(
            self, "UserPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            removal_policy=RemovalPolicy.DESTROY,
        )

        google_client_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "GoogleClientSecret",
            f"ssm-transcriber/{self.env_name}/google-oauth-client-secret",
        )
        google_client_id = ssm.StringParameter.value_for_string_parameter(
            self, f"/ssm-transcriber/{self.env_name}/google-oauth-client-id"
        )
        google_idp = cognito.UserPoolIdentityProviderGoogle(
            self, "GoogleIdp",
            user_pool=self.user_pool,
            client_id=google_client_id,
            client_secret_value=google_client_secret.secret_value,
            scopes=["openid", "email", "profile"],
            attribute_mapping=cognito.AttributeMapping(
                email=cognito.ProviderAttribute.GOOGLE_EMAIL
            ),
        )

        invite_fn = lambda_.Function(
            self, "InviteGateFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="transcriber.hosted.handlers.invite_gate.handler",
            code=_lambda_code(),
            environment={"HOSTED_TABLE": self.table.table_name},
        )
        self.table.grant_read_data(invite_fn)
        self.user_pool.add_trigger(
            cognito.UserPoolOperation.PRE_SIGN_UP, invite_fn
        )

        self.user_pool_client = self.user_pool.add_client(
            "WebClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL],
                callback_urls=["http://localhost:5173/callback"],
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.GOOGLE
            ],
        )
        self.user_pool_client.node.add_dependency(google_idp)

        self.user_pool.add_domain(
            "HostedUiDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"ssm-transcriber-{self.env_name}"
            ),
        )
        # Resources added in Groups B–E.
