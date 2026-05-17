"""Operator seed script for the hosted stack.

Two jobs, deliberately split (chicken-egg the plan splits):

  invite   — write invited-user ``#PROFILE`` rows BEFORE first sign-in.
             The invite-gate rejects anyone without a #PROFILE, so this
             must run before the user signs in via Cognito.
  fixture  — write a committed transcript fixture AFTER the invited user
             has a Cognito ``sub``. manifest.json is written LAST so the
             prefix only becomes reader-visible once fully committed
             (commit-marker rule, Codex P2).

The pure builders (``build_profile_item`` / ``fixture_objects``) carry
the tested logic; the boto3 subcommand wrappers are thin and exercised
by the user-run Task 17. This is an operator script, not library code,
so ``print`` is acceptable for non-sensitive count summaries.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# infra/ is outside the package; ensure the repo src/ is importable so
# seed keys and handler keys come from the SAME module (no drift).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from transcriber.hosted.s3keys import (  # noqa: E402
    manifest_key,
    raw_key,
    transcript_key,
)

_FIXTURE_TRANSCRIPT = """---
title: Seed fixture transcript
source: seed
---
# Seed fixture transcript

This is a committed seed fixture written by ``infra/seed.py``.
"""

_FIXTURE_RAW = '{"text": "Seed fixture transcript", "segments": []}'

# manifest.json is the commit marker — its presence makes the prefix visible.
_FIXTURE_MANIFEST = b'{"committed": true}'


# --- pure builders (unit-tested; no AWS) ----------------------------------


def build_profile_item(email: str, budget: int = 5) -> dict:
    """Build an invited-user #PROFILE item.

    ``monthly_budget_usd`` is stored as a STRING — the project's
    DynamoDB number-as-string convention that get_me/invite_gate read.
    """
    return {
        "PK": f"USER#{email}",
        "SK": "#PROFILE",
        "email": email,
        "monthly_budget_usd": str(budget),
    }


def fixture_objects(sub: str, job_id: str = "seed-job") -> list[tuple[str, bytes]]:
    """Build the three transcript-fixture objects, manifest LAST.

    Keys come from ``transcriber.hosted.s3keys`` so they can never drift
    from the handlers. Ordering matters: manifest.json is the commit
    marker and MUST be the final element so callers write it last.
    """
    return [
        (transcript_key(sub, job_id), _FIXTURE_TRANSCRIPT.encode("utf-8")),
        (raw_key(sub, job_id), _FIXTURE_RAW.encode("utf-8")),
        (manifest_key(sub, job_id), _FIXTURE_MANIFEST),
    ]


# --- thin boto3 subcommand wrappers (untested-by-design) ------------------


def _cmd_invite(args: argparse.Namespace) -> None:
    import boto3
    from botocore.exceptions import ClientError

    table_name = args.table or os.environ.get("HOSTED_TABLE")
    if not table_name:
        raise SystemExit("missing table: pass --table or set HOSTED_TABLE")
    emails = [e.strip() for e in args.emails.split(",") if e.strip()]
    table = boto3.resource("dynamodb").Table(table_name)
    invited = 0
    skipped = 0
    for email in emails:
        item = build_profile_item(email, args.budget)
        if args.overwrite:
            # Intentional reset: omit the guard so an existing row is replaced.
            table.put_item(Item=item)
            print(f"overwrote: {email}")
            invited += 1
            continue
        try:
            table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as exc:
            if (
                exc.response.get("Error", {}).get("Code")
                == "ConditionalCheckFailedException"
            ):
                # Non-destructive: an existing #PROFILE is left untouched so a
                # re-run never silently resets monthly_budget_usd (Codex P4).
                print(f"skipped (already invited): {email}")
                skipped += 1
                continue
            raise
        invited += 1
    print(f"invited {invited}, skipped {skipped} (into {table_name})")


def _cmd_fixture(args: argparse.Namespace) -> None:
    import boto3

    bucket = args.bucket or os.environ.get("TRANSCRIPTS_BUCKET")
    if not bucket:
        raise SystemExit("missing bucket: pass --bucket or set TRANSCRIPTS_BUCKET")
    s3 = boto3.client("s3")
    objs = fixture_objects(args.sub, args.job_id)
    for key, body in objs:  # in order — manifest.json written LAST
        s3.put_object(Bucket=bucket, Key=key, Body=body)
    print(f"wrote {len(objs)} fixture object(s) under {args.sub}/{args.job_id}/ in {bucket}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the hosted stack.")
    sub = parser.add_subparsers(dest="command", required=True)

    invite = sub.add_parser("invite", help="write invited-user #PROFILE rows")
    invite.add_argument("--emails", required=True, help="comma-separated emails")
    invite.add_argument("--budget", type=int, default=5)
    invite.add_argument("--table", default=None, help="defaults to $HOSTED_TABLE")
    invite.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing #PROFILE (intentional reset; off by default)",
    )
    invite.set_defaults(func=_cmd_invite)

    fixture = sub.add_parser("fixture", help="write a committed transcript fixture")
    fixture.add_argument("--sub", required=True, help="the user's Cognito sub")
    fixture.add_argument("--job-id", default="seed-job")
    fixture.add_argument("--bucket", default=None, help="defaults to $TRANSCRIPTS_BUCKET")
    fixture.set_defaults(func=_cmd_fixture)

    return parser


if __name__ == "__main__":
    _args = _build_parser().parse_args()
    _args.func(_args)
