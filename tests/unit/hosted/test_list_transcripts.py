import json

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
    assert [j["job_id"] for j in body["transcripts"]] == ["j1"]   # j2 has no manifest


def test_user_isolation(bucket):
    out = handler(_event("other"), None)
    assert json.loads(out["body"])["transcripts"] == []
