"""Cognito Pre-Sign-up Lambda trigger: reject un-invited Google accounts.

Event shape is the Task-0 pinned trigger payload. Raising from the trigger
makes Cognito deny the sign-up (spec Scenario 2: "not invited" message).

Per the Task-0 pin (requirements.md "#### 7a pins", AWS Cognito Developer
Guide, retrieved 2026-05-16): "your pre sign-up trigger can automatically
confirm users for the `PreSignUp_SignUp` trigger source, but return the
event unchanged for external and administrator-created users." So this
handler branches on `event["triggerSource"]` and never writes
auto-confirm flags for the external-provider path.

No print(); structured logging only (F8).
"""

from __future__ import annotations

import logging
import os

import boto3

log = logging.getLogger(__name__)


def _require_invite(event: dict) -> dict:
    """#PROFILE invite lookup; raise to deny un-invited accounts.

    Returns the event unchanged on success — per the pin, external and
    self-service-in-an-invite-only-pool sign-ups are not auto-confirmed
    here.
    """
    email = event["request"]["userAttributes"]["email"]
    table_name = os.environ["HOSTED_TABLE"]
    table = boto3.resource("dynamodb").Table(table_name)
    item = table.get_item(Key={"PK": f"USER#{email}", "SK": "#PROFILE"}).get("Item")
    if not item:
        log.info("invite_gate.reject", extra={"email_present": bool(email)})
        raise PermissionError(
            "This Google account is not invited. Ask the admin for an invite."
        )
    log.info("invite_gate.allow")
    return event


def handler(event: dict, _context) -> dict:
    trigger = event["triggerSource"]
    if trigger == "PreSignUp_ExternalProvider":
        # Federated Google first sign-in: the path this gate exists for.
        # Pin: "return the event unchanged for external ... users" — so on
        # success we return the event with response untouched (no
        # autoConfirmUser/autoVerifyEmail writes).
        return _require_invite(event)
    if trigger == "PreSignUp_AdminCreateUser":
        # Admin-created users are invited by definition. Pin: "return the
        # event unchanged for ... administrator-created users." No gate,
        # no mutation, no DynamoDB lookup.
        log.info("invite_gate.admin_create_passthrough")
        return event
    if trigger == "PreSignUp_SignUp":
        # Self-service sign-up. Structurally unreachable while the user
        # pool sets self_sign_up_enabled=False, but the gate enforces the
        # invite-only policy on its own logic rather than relying on that
        # CDK setting: same #PROFILE check, deny if un-invited. The pin
        # permits auto-confirm for this source; we deliberately do not, so
        # invite-only stays the single source of truth.
        return _require_invite(event)
    # Unknown trigger source: deny by default — invite-only pools should
    # never invoke this Lambda on an unrecognised pre-sign-up path.
    log.info("invite_gate.reject_unknown_trigger")
    raise PermissionError("Unsupported sign-up path for this user pool.")
