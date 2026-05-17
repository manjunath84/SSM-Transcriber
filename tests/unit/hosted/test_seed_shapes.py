"""Pure-builder tests for infra/seed.py — NEVER touches AWS.

We import the builder functions directly and assert their shapes match
what invite_gate/get_me read (#PROFILE) and what the handlers' s3keys
module produces (transcript fixture), so seed + handlers can't drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from transcriber.hosted.s3keys import manifest_key, raw_key, transcript_key

# infra/ is outside the package; add it so we can import the operator script.
_INFRA = Path(__file__).resolve().parents[3] / "infra"
if str(_INFRA) not in sys.path:
    sys.path.insert(0, str(_INFRA))

import seed  # noqa: E402


def test_build_profile_item_shape() -> None:
    item = seed.build_profile_item("a@x.com", 5)
    assert item == {
        "PK": "USER#a@x.com",
        "SK": "#PROFILE",
        "email": "a@x.com",
        "monthly_budget_usd": "5",
    }
    # budget stored as a STRING (get_me/invite_gate read it as a string).
    assert isinstance(item["monthly_budget_usd"], str)


def test_build_profile_item_default_budget() -> None:
    item = seed.build_profile_item("b@x.com")
    assert item["monthly_budget_usd"] == "5"


def test_fixture_objects_keys_match_s3keys_module() -> None:
    objs = seed.fixture_objects("sub-123", "job-9")
    assert len(objs) == 3
    keys = [k for k, _ in objs]
    assert keys == [
        transcript_key("sub-123", "job-9"),
        raw_key("sub-123", "job-9"),
        manifest_key("sub-123", "job-9"),
    ]


def test_fixture_objects_manifest_is_last() -> None:
    objs = seed.fixture_objects("sub-123", "job-9")
    # commit-marker ordering: manifest.json written LAST (index 2).
    last_key, last_body = objs[2]
    assert last_key == manifest_key("sub-123", "job-9")
    assert json.loads(last_body) == {"committed": True}
    assert last_body == b'{"committed": true}'


def test_fixture_objects_default_job_id() -> None:
    objs = seed.fixture_objects("sub-123")
    assert objs[0][0] == transcript_key("sub-123", "seed-job")


def test_fixture_objects_bodies_are_valid() -> None:
    objs = seed.fixture_objects("sub-123", "job-9")
    (t_key, t_body), (r_key, r_body), (m_key, m_body) = objs
    # transcript.md: YAML frontmatter then a markdown heading.
    text = t_body.decode("utf-8")
    assert text.startswith("---\n")
    assert "\n---\n" in text
    assert "# " in text
    # result.raw.json + manifest.json: valid JSON.
    json.loads(r_body)
    assert json.loads(m_body) == {"committed": True}
