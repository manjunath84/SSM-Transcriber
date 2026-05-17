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


def _event(email: str, trigger: str = "PreSignUp_ExternalProvider") -> dict:
    # Shape per the requirements.md "#### 7a pins" pre-sign-up trigger event.
    return {
        "triggerSource": trigger,
        "request": {"userAttributes": {"email": email}},
        "response": {},
    }


def test_external_provider_invited_returns_event_unchanged(table):
    # Pin: "return the event unchanged for external ... users" — no
    # autoConfirmUser/autoVerifyEmail writes.
    table.put_item(
        Item={
            "PK": "USER#wife@example.com",
            "SK": "#PROFILE",
            "email": "wife@example.com",
            "monthly_budget_usd": "5",
        }
    )
    out = handler(_event("wife@example.com"), None)
    assert out["response"] == {}
    assert "autoConfirmUser" not in out["response"]
    assert "autoVerifyEmail" not in out["response"]


def test_external_provider_uninvited_rejected(table):
    with pytest.raises(PermissionError) as ei:
        handler(_event("stranger@example.com"), None)
    assert "not invited" in str(ei.value).lower()


def test_admin_create_user_passes_through_without_ddb(monkeypatch):
    # Admin-created users are invited by definition. Pin: return unchanged.
    # No `table` fixture / no HOSTED_TABLE env: proves the branch genuinely
    # skips the DynamoDB lookup rather than coincidentally finding nothing.
    monkeypatch.delenv("HOSTED_TABLE", raising=False)
    event = _event("admin-made@example.com", trigger="PreSignUp_AdminCreateUser")
    out = handler(event, None)
    assert out is event
    assert out["response"] == {}


def test_self_service_signup_uninvited_rejected(table):
    # Structurally unreachable (self_sign_up_enabled=False) but the gate
    # enforces invite-only on its own logic regardless.
    with pytest.raises(PermissionError) as ei:
        handler(
            _event("self-signup@example.com", trigger="PreSignUp_SignUp"), None
        )
    assert "not invited" in str(ei.value).lower()


def test_self_service_signup_invited_passes(table):
    table.put_item(
        Item={
            "PK": "USER#invited@example.com",
            "SK": "#PROFILE",
            "email": "invited@example.com",
            "monthly_budget_usd": "5",
        }
    )
    out = handler(
        _event("invited@example.com", trigger="PreSignUp_SignUp"), None
    )
    assert out["response"] == {}


def test_unknown_trigger_source_denied(table):
    with pytest.raises(PermissionError):
        handler(_event("x@example.com", trigger="PreSignUp_Something"), None)
