"""DELETE /transcripts/{id} — delete a committed transcript (manifest-first)."""

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
        # De-commit linearization point: delete the manifest as its OWN
        # successful call FIRST. A crash after this leaves an invisible
        # prefix (Codex P2), never a committed half-transcript. A single
        # batched delete_objects does NOT guarantee this ordering.
        s3.delete_object(Bucket=bucket, Key=manifest_key(sub, job_id))
        # Now invisible — the remaining two are safe to batch.
        s3.delete_objects(
            Bucket=bucket,
            Delete={
                "Objects": [
                    {"Key": transcript_key(sub, job_id)},
                    {"Key": raw_key(sub, job_id)},
                ]
            },
        )
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"deleted": job_id}),
        }
    except Exception as exc:  # boundary handler: mapped via to_response, not swallowed
        return to_response(exc)
