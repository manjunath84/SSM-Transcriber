"""GET /users/me — the caller's #PROFILE (budget pill source). 7a: no usage math."""

from __future__ import annotations

import json
import os

import boto3

from transcriber.hosted.errors import NotFound, to_response


def handler(event: dict, _context) -> dict:
    try:
        email = event["requestContext"]["authorizer"]["jwt"]["claims"]["email"]
        table = boto3.resource("dynamodb").Table(os.environ["HOSTED_TABLE"])
        item = table.get_item(
            Key={"PK": f"USER#{email}", "SK": "#PROFILE"}
        ).get("Item")
        if not item:
            raise NotFound("profile not found")
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(
                {"email": item["email"],
                 "monthly_budget_usd": item["monthly_budget_usd"]}
            ),
        }
    except Exception as exc:  # boundary handler: mapped via to_response, not swallowed
        return to_response(exc)
