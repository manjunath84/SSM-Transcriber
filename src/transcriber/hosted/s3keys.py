"""S3 key helpers + the manifest.json commit-marker visibility rule.

A job prefix is reader-visible ONLY when manifest.json exists (spec
"Atomic output writes", Codex P2): a partial write (one object, crash
before the marker) yields an invisible prefix, never a half-transcript.
"""

from __future__ import annotations

TRANSCRIPT_NAME = "transcript.md"
RAW_NAME = "result.raw.json"
MANIFEST_NAME = "manifest.json"


def job_prefix(sub: str) -> str:
    return f"{sub}/"


def transcript_key(sub: str, job_id: str) -> str:
    return f"{sub}/{job_id}/{TRANSCRIPT_NAME}"


def raw_key(sub: str, job_id: str) -> str:
    return f"{sub}/{job_id}/{RAW_NAME}"


def manifest_key(sub: str, job_id: str) -> str:
    return f"{sub}/{job_id}/{MANIFEST_NAME}"


def visible_job_ids(sub: str, keys: list[str]) -> list[str]:
    """Job ids under ``sub/`` that have a manifest.json (committed jobs only)."""
    committed: list[str] = []
    for key in keys:
        parts = key.split("/")
        if len(parts) == 3 and parts[0] == sub and parts[2] == MANIFEST_NAME:
            committed.append(parts[1])
    return sorted(committed)
