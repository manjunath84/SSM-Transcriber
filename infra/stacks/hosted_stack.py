from __future__ import annotations

import os

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_authorizers as apigwv2_authorizers
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as cloudfront_origins
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
    # CDK_SKIP_BUNDLING=1 → no-Docker path. assertions.Template tests (and a
    # Dockerless `cdk synth`) assert resource SHAPES (Cognito/routes/buckets),
    # not Lambda code content, so a plain unbundled asset is sufficient and
    # avoids requiring Docker to run the infra unit tests / synth locally.
    # Real `cdk deploy` (user Task 17 / Docker-enabled CI) leaves the var
    # unset and gets the correct pip-bundled package.
    if os.environ.get("CDK_SKIP_BUNDLING") == "1":
        return lambda_.Code.from_asset("../src/transcriber/hosted")
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

        self.user_pool_domain = self.user_pool.add_domain(
            "HostedUiDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"ssm-transcriber-{self.env_name}"
            ),
        )

        # --- SPA hosting (S3 + CloudFront) -----------------------------------
        # Created before the Cognito app client so the CloudFront callback URL
        # can be passed at client-creation time (cleanest approach — avoids
        # post-hoc o_auth escape-hatch mutation).
        self.spa_bucket = s3.Bucket(
            self,
            "SpaBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,  # $0 teardown lever
            auto_delete_objects=True,
        )
        self.distribution = cloudfront.Distribution(
            self,
            "SpaDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=cloudfront_origins.S3BucketOrigin.with_origin_access_control(
                    self.spa_bucket
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            error_responses=[
                # SPA client-side routing: serve index.html for 403/404.
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )
        cloudfront_url = f"https://{self.distribution.distribution_domain_name}"

        self.user_pool_client = self.user_pool.add_client(
            "WebClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL],
                callback_urls=[
                    "http://localhost:5173/callback",
                    f"{cloudfront_url}/callback",
                ],
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.GOOGLE
            ],
        )
        self.user_pool_client.node.add_dependency(google_idp)

        # --- API (API Gateway v2 HTTP API + Cognito JWT authorizer) ----------
        _env_bucket = {"TRANSCRIPTS_BUCKET": self.transcripts_bucket.bucket_name}
        list_fn = lambda_.Function(
            self, "ListTranscriptsFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="transcriber.hosted.handlers.list_transcripts.handler",
            code=_lambda_code(),
            environment=_env_bucket,
        )
        get_fn = lambda_.Function(
            self, "GetTranscriptFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="transcriber.hosted.handlers.get_transcript.handler",
            code=_lambda_code(),
            environment=_env_bucket,
        )
        delete_fn = lambda_.Function(
            self, "DeleteTranscriptFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="transcriber.hosted.handlers.delete_transcript.handler",
            code=_lambda_code(),
            environment=_env_bucket,
        )
        get_me_fn = lambda_.Function(
            self, "GetMeFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="transcriber.hosted.handlers.get_me.handler",
            code=_lambda_code(),
            environment={"HOSTED_TABLE": self.table.table_name},
        )
        self.transcripts_bucket.grant_read(list_fn)
        self.transcripts_bucket.grant_read(get_fn)
        self.transcripts_bucket.grant_read_write(delete_fn)
        self.table.grant_read_data(get_me_fn)

        # Pinned shape (Task-0 pin): HttpUserPoolAuthorizer(id, pool, ...) as
        # the HttpApi default_authorizer. HttpLambdaIntegration is the
        # Lambda-proxy integration (an extension of the pin's HttpUrlIntegration
        # example — same module, same add_routes contract).
        authorizer = apigwv2_authorizers.HttpUserPoolAuthorizer(
            "JwtAuthorizer",
            self.user_pool,
            user_pool_clients=[self.user_pool_client],
        )
        http_api = apigwv2.HttpApi(
            self, "HttpApi",
            default_authorizer=authorizer,
            cors_preflight=apigwv2.CorsPreflightOptions(
                # Permissive for 7a: pinning the exact CloudFront origin
                # pre-deploy is circular (distribution domain is only known
                # post-synth). Tightened to the CloudFront origin in a later
                # slice once the domain is a stable deploy input.
                allow_origins=["*"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.DELETE,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["authorization", "content-type"],
            ),
        )
        http_api.add_routes(
            path="/transcripts",
            methods=[apigwv2.HttpMethod.GET],
            integration=apigwv2_integrations.HttpLambdaIntegration(
                "ListIntegration", list_fn
            ),
        )
        http_api.add_routes(
            path="/transcripts/{id}",
            methods=[apigwv2.HttpMethod.GET],
            integration=apigwv2_integrations.HttpLambdaIntegration(
                "GetIntegration", get_fn
            ),
        )
        http_api.add_routes(
            path="/transcripts/{id}",
            methods=[apigwv2.HttpMethod.DELETE],
            integration=apigwv2_integrations.HttpLambdaIntegration(
                "DeleteIntegration", delete_fn
            ),
        )
        http_api.add_routes(
            path="/users/me",
            methods=[apigwv2.HttpMethod.GET],
            integration=apigwv2_integrations.HttpLambdaIntegration(
                "GetMeIntegration", get_me_fn
            ),
        )

        # --- Outputs ---------------------------------------------------------
        CfnOutput(self, "ApiBaseUrl", value=http_api.url or "")
        CfnOutput(self, "CloudFrontUrl", value=cloudfront_url)
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(
            self, "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
        )
        CfnOutput(self, "CognitoDomain", value=self.user_pool_domain.base_url())
