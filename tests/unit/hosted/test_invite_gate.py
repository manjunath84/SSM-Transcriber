import boto3
import pytest
from moto import mock_aws

from transcriber.hosted.handlers.invite_gate import handler


@pytest.fixture()
def table(monkeypatch):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        t = ddb.create_table(
            TableName="HostedTable",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("HOSTED_TABLE", "HostedTable")
        # Required: handlers call boto3 with no explicit region; moto 5
        # won't auto-set it -> NoRegionError before any assertion runs.
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        yield t


def _event(email: str) -> dict:
    # Shape per the requirements.md "#### 7a pins" federated-signin trigger event.
    return {
        "triggerSource": "PreSignUp_ExternalProvider",
        "request": {"userAttributes": {"email": email}},
        "response": {},
    }


def test_invited_user_passes(table):
    table.put_item(
        Item={
            "PK": "USER#wife@example.com",
            "SK": "#PROFILE",
            "email": "wife@example.com",
            "monthly_budget_usd": "5",
        }
    )
    out = handler(_event("wife@example.com"), None)
    assert out["response"]["autoConfirmUser"] is True


def test_uninvited_user_rejected(table):
    with pytest.raises(Exception) as ei:
        handler(_event("stranger@example.com"), None)
    assert "not invited" in str(ei.value).lower()
