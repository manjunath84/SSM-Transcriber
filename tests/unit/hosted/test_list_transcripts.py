import json
import time

import boto3
import pytest
from moto import mock_aws

from transcriber.hosted.handlers.list_transcripts import handler


@pytest.fixture()
def bucket(monkeypatch):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        s3.put_object(Bucket="test-bucket", Key="sub1/j1/transcript.md", Body=b"# t")
        s3.put_object(Bucket="test-bucket", Key="sub1/j1/manifest.json", Body=b"{}")
        s3.put_object(Bucket="test-bucket", Key="sub1/j2/transcript.md", Body=b"# partial")
        # j3: a SECOND committed job whose manifest is written LAST so its
        # S3 LastModified is strictly newer than j1's. This exercises the
        # newest-first sort (handler sorts manifest LastModified desc) — a
        # regression to unsorted/oldest-first would flip the order below.
        time.sleep(1.05)  # ensure a distinct (>=1s) S3 LastModified vs j1
        s3.put_object(Bucket="test-bucket", Key="sub1/j3/transcript.md", Body=b"# newer")
        s3.put_object(Bucket="test-bucket", Key="sub1/j3/manifest.json", Body=b"{}")
        monkeypatch.setenv("TRANSCRIPTS_BUCKET", "test-bucket")
        # Required: handlers call boto3 with no explicit region; moto 5
        # won't auto-set it -> NoRegionError before any assertion. Tasks 10
        # & 11 reuse this exact fixture, so this line covers them too.
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        yield s3


def _event(sub: str) -> dict:
    return {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": sub}}}}}


def test_lists_only_committed_jobs(bucket):
    out = handler(_event("sub1"), None)
    body = json.loads(out["body"])
    # j1 + j3 are committed (have manifest.json); j2 is manifest-gated out.
    assert {j["job_id"] for j in body["transcripts"]} == {"j1", "j3"}


def test_committed_jobs_are_newest_first(bucket):
    out = handler(_event("sub1"), None)
    body = json.loads(out["body"])
    # j3's manifest was written after j1's, so newest-first must put j3 ahead
    # of j1. An unsorted/oldest-first regression would yield ["j1", "j3"].
    assert [j["job_id"] for j in body["transcripts"]] == ["j3", "j1"]


def test_user_isolation(bucket):
    out = handler(_event("other"), None)
    assert json.loads(out["body"])["transcripts"] == []
