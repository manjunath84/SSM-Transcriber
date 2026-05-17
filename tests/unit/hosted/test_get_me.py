import json

import boto3
import pytest
from moto import mock_aws

from transcriber.hosted.handlers.get_me import handler


@pytest.fixture()
def table(monkeypatch):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="HostedTable",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                       {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                                  {"AttributeName": "SK", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("HOSTED_TABLE", "HostedTable")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        yield ddb.Table("HostedTable")


def _event(email: str) -> dict:
    return {"requestContext": {"authorizer": {"jwt": {"claims": {"email": email}}}}}


def test_returns_profile_fields(table):
    table.put_item(Item={"PK": "USER#wife@example.com", "SK": "#PROFILE",
                         "email": "wife@example.com", "monthly_budget_usd": "5"})
    body = json.loads(handler(_event("wife@example.com"), None)["body"])
    assert body == {"email": "wife@example.com", "monthly_budget_usd": "5"}


def test_missing_profile_is_404(table):
    assert handler(_event("ghost@example.com"), None)["statusCode"] == 404
