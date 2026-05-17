import json

import boto3
import pytest
from moto import mock_aws

from transcriber.hosted.handlers.get_transcript import handler


@pytest.fixture()
def bucket(monkeypatch):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        s3.put_object(
            Bucket="test-bucket", Key="sub1/j1/transcript.md", Body=b"# hello"
        )
        s3.put_object(
            Bucket="test-bucket", Key="sub1/j1/result.raw.json", Body=b"{}"
        )
        s3.put_object(Bucket="test-bucket", Key="sub1/j1/manifest.json", Body=b"{}")
        s3.put_object(
            Bucket="test-bucket", Key="sub1/j2/transcript.md", Body=b"# partial"
        )
        monkeypatch.setenv("TRANSCRIPTS_BUCKET", "test-bucket")
        # Required: handlers call boto3 with no explicit region; moto 5
        # won't auto-set it -> NoRegionError before any assertion.
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        yield s3


def _event(sub: str, job_id: str) -> dict:
    return {
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": sub}}}},
        "pathParameters": {"id": job_id},
    }


def test_get_returns_markdown_for_committed_job(bucket):
    out = handler(_event("sub1", "j1"), None)
    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body == {"markdown": "# hello", "raw_present": True}


def test_get_missing_manifest_is_404(bucket):
    out = handler(_event("sub1", "j2"), None)
    assert out["statusCode"] == 404


def test_get_other_users_job_is_404(bucket):
    out = handler(_event("other", "j1"), None)
    assert out["statusCode"] == 404
