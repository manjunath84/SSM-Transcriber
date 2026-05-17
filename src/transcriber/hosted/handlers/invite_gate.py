"""Cognito federated-signin Lambda trigger: reject un-invited Google accounts.

Event shape is the Task-0 pinned trigger payload. Raising from the trigger
makes Cognito deny the sign-in (spec Scenario 2: "not invited" message).
No print(); structured logging only (F8).
"""

from __future__ import annotations

import logging
import os

import boto3

log = logging.getLogger(__name__)


def handler(event: dict, _context) -> dict:
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
    event["response"]["autoConfirmUser"] = True
    event["response"]["autoVerifyEmail"] = True
    return event
