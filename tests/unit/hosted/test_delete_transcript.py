import json

import boto3
import pytest
from moto import mock_aws

from transcriber.hosted.handlers.delete_transcript import handler


@pytest.fixture()
def bucket(monkeypatch):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        # sub1/j1: a fully committed job (all three objects).
        s3.put_object(Bucket="test-bucket", Key="sub1/j1/transcript.md", Body=b"# t")
        s3.put_object(Bucket="test-bucket", Key="sub1/j1/result.raw.json", Body=b"{}")
        s3.put_object(Bucket="test-bucket", Key="sub1/j1/manifest.json", Body=b"{}")
        # other/j1: a different user's committed job (must stay untouched).
        s3.put_object(Bucket="test-bucket", Key="other/j1/transcript.md", Body=b"# o")
        s3.put_object(Bucket="test-bucket", Key="other/j1/result.raw.json", Body=b"{}")
        s3.put_object(Bucket="test-bucket", Key="other/j1/manifest.json", Body=b"{}")
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


def _exists(s3, key: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        s3.head_object(Bucket="test-bucket", Key=key)
        return True
    except ClientError:
        return False


def test_delete_removes_all_three_objects(bucket):
    out = handler(_event("sub1", "j1"), None)
    assert out["statusCode"] == 200
    assert json.loads(out["body"]) == {"deleted": "j1"}
    assert not _exists(bucket, "sub1/j1/manifest.json")
    assert not _exists(bucket, "sub1/j1/transcript.md")
    assert not _exists(bucket, "sub1/j1/result.raw.json")


def test_delete_foreign_job_is_404_and_leaves_objects(bucket):
    out = handler(_event("sub1", "j1"), None)  # warm path: sub1 owns j1
    assert out["statusCode"] == 200
    # "other" still owns its own j1; sub1 cannot reach it.
    out2 = handler(_event("sub1", "nope"), None)
    assert out2["statusCode"] == 404
    assert _exists(bucket, "other/j1/manifest.json")
    assert _exists(bucket, "other/j1/transcript.md")
    assert _exists(bucket, "other/j1/result.raw.json")


def test_delete_other_users_job_is_404_and_leaves_objects(bucket):
    out = handler(_event("sub1", "j1_does_not_belong"), None)
    assert out["statusCode"] == 404
    # The real owner's objects are untouched.
    assert _exists(bucket, "other/j1/manifest.json")
    assert _exists(bucket, "other/j1/transcript.md")
    assert _exists(bucket, "other/j1/result.raw.json")


def test_delete_is_idempotent(bucket):
    first = handler(_event("sub1", "j1"), None)
    assert first["statusCode"] == 200
    # Second delete of the now-gone job: 404, no exception/500.
    second = handler(_event("sub1", "j1"), None)
    assert second["statusCode"] == 404
    # Never-existed job: also 404, no crash.
    third = handler(_event("sub1", "never"), None)
    assert third["statusCode"] == 404


def test_manifest_deleted_before_other_objects(bucket, monkeypatch):
    """The manifest delete must be its own successful call, issued BEFORE
    the transcript.md / result.raw.json deletes. We wrap the real boto3
    client in a recorder that crashes immediately after the manifest
    delete returns; the manifest must then be gone while the other two
    survive -- proving manifest-first ordering as a standalone call (not
    batched with the other two)."""
    real = boto3.client("s3", region_name="us-east-1")

    class Boom(RuntimeError):
        pass

    class Recorder:
        def __init__(self, inner):
            self._inner = inner
            self.calls: list[tuple[str, tuple]] = []

        def head_object(self, **kw):
            self.calls.append(("head_object", (kw.get("Key"),)))
            return self._inner.head_object(**kw)

        def delete_object(self, **kw):
            key = kw.get("Key")
            self.calls.append(("delete_object", (key,)))
            self._inner.delete_object(**kw)
            # Manifest delete has now returned successfully; crash before
            # any other delete can run.
            raise Boom("crash immediately after manifest delete")

        def delete_objects(self, **kw):
            keys = tuple(o["Key"] for o in kw["Delete"]["Objects"])
            self.calls.append(("delete_objects", keys))
            return self._inner.delete_objects(**kw)

    rec = Recorder(real)
    monkeypatch.setattr(boto3, "client", lambda *a, **k: rec)

    out = handler(_event("sub1", "j1"), None)
    # Boundary handler maps the injected crash to a 500.
    assert out["statusCode"] == 500

    # First mutating S3 call after the HEAD must be a STANDALONE
    # delete_object for exactly the manifest key.
    mutating = [c for c in rec.calls if c[0] in ("delete_object", "delete_objects")]
    assert mutating[0] == ("delete_object", ("sub1/j1/manifest.json",))

    # The crash happened right after the manifest delete returned, so:
    # manifest is GONE (de-committed) but transcript/raw still present.
    assert not _exists(real, "sub1/j1/manifest.json")
    assert _exists(real, "sub1/j1/transcript.md")
    assert _exists(real, "sub1/j1/result.raw.json")
