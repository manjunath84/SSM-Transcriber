from transcriber.hosted.s3keys import (
    job_prefix,
    manifest_key,
    raw_key,
    transcript_key,
    visible_job_ids,
)


def test_key_builders() -> None:
    assert transcript_key("sub1", "j1") == "sub1/j1/transcript.md"
    assert raw_key("sub1", "j1") == "sub1/j1/result.raw.json"
    assert manifest_key("sub1", "j1") == "sub1/j1/manifest.json"
    assert job_prefix("sub1") == "sub1/"


def test_visible_job_ids_requires_manifest() -> None:
    keys = [
        "sub1/j1/transcript.md",
        "sub1/j1/result.raw.json",
        "sub1/j1/manifest.json",   # committed
        "sub1/j2/transcript.md",   # partial — no manifest
        "sub1/j2/result.raw.json",
    ]
    assert visible_job_ids("sub1", keys) == ["j1"]
