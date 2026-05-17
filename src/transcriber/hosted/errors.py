"""Hosted error taxonomy → API Gateway proxy responses. No secret leakage (F8)."""

from __future__ import annotations

import json


class HostedError(Exception):
    status = 500


class NotFound(HostedError):
    status = 404


class Forbidden(HostedError):
    status = 403


class BadRequest(HostedError):
    status = 400


def to_response(exc: Exception) -> dict:
    if isinstance(exc, HostedError):
        status, message = exc.status, str(exc)
    else:
        status, message = 500, "internal error"
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": message}),
    }
