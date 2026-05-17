from __future__ import annotations

from aws_cdk import Stack
from constructs import Construct


class HostedStack(Stack):
    """Single stack for Phase 7 hosted UI. Grows per slice; 7a = auth + viewer."""

    def __init__(self, scope: Construct, cid: str, *, env_name: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        self.env_name = env_name
        # Resources added in Groups B–E.
