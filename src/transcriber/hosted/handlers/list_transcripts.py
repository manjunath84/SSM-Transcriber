"""GET /transcripts — list the caller's committed transcripts (newest-first)."""

from __future__ import annotations

import json
import os

import boto3

from transcriber.hosted.errors import to_response
from transcriber.hosted.s3keys import job_prefix, manifest_key, visible_job_ids


def handler(event: dict, _context) -> dict:
    try:
        sub = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
        bucket = os.environ["TRANSCRIPTS_BUCKET"]
        s3 = boto3.client("s3")
        keys: list[str] = []
        token: str | None = None
        while True:
            kw = {"Bucket": bucket, "Prefix": job_prefix(sub)}
            if token:
                kw["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kw)
            keys += [o["Key"] for o in resp.get("Contents", [])]
            if not resp.get("IsTruncated"):
                break
            token = resp["NextContinuationToken"]
        jobs = []
        for jid in visible_job_ids(sub, keys):
            head = s3.head_object(Bucket=bucket, Key=manifest_key(sub, jid))
            jobs.append({"job_id": jid,
                         "last_modified": head["LastModified"].isoformat()})
        jobs.sort(key=lambda j: j["last_modified"], reverse=True)
        return {"statusCode": 200,
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"transcripts": jobs})}
    except Exception as exc:  # boundary handler: error is mapped via to_response, not swallowed
        return to_response(exc)
