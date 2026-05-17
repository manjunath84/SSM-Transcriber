from __future__ import annotations

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_s3 as s3
from constructs import Construct


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
        # Resources added in Groups B–E.
