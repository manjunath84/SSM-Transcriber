"""GET /transcripts/{id} — return one committed transcript's markdown."""

from __future__ import annotations

import json
import os

import boto3
from botocore.exceptions import ClientError

from transcriber.hosted.errors import NotFound, to_response
from transcriber.hosted.s3keys import manifest_key, raw_key, transcript_key


def handler(event: dict, _context) -> dict:
    try:
        sub = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
        job_id = event["pathParameters"]["id"]
        bucket = os.environ["TRANSCRIPTS_BUCKET"]
        s3 = boto3.client("s3")
        try:
            s3.head_object(Bucket=bucket, Key=manifest_key(sub, job_id))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise NotFound("transcript not found") from exc
            raise
        text = (
            s3.get_object(Bucket=bucket, Key=transcript_key(sub, job_id))["Body"]
            .read()
            .decode("utf-8")
        )
        raw_present = True
        try:
            s3.head_object(Bucket=bucket, Key=raw_key(sub, job_id))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                raw_present = False
            else:
                raise
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"markdown": text, "raw_present": raw_present}),
        }
    except Exception as exc:  # boundary handler: mapped via to_response, not swallowed
        return to_response(exc)
