"""Two-gate spend check for paid transcription calls.

Per F4 in ``docs/PLAN.md``:

- **Gate 1 (configured):** is there a usable key/endpoint for this provider?
- **Gate 2 (allowed):** does the current budget permit paid use?

Slice 1 hardcodes the rate around AssemblyAI; the provider-agnostic
generalization lands in Phase 5 (full provider registry + per-provider
rate hooks). The function below takes ``key_configured`` and the rate as
arguments rather than reading ``settings`` itself, so it stays pure and
trivially unit-testable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


# AssemblyAI's published rate for the ``best`` tier (per docs/PLAN.md §Phase 5).
ASSEMBLYAI_RATE_PER_MINUTE_USD: float = 0.009

# Above this estimate, ``check`` emits a louder warning. ``--yes`` still
# bypasses the confirmation prompt; the warning is informational, not a hard
# gate. The hard gates remain Gate 1 and Gate 2.
SOFT_CAP_USD: float = 5.0


class BudgetError(RuntimeError):
    """Gate 1 or Gate 2 failed. CLI maps this to exit code 2 (config)."""


def estimate_assemblyai_cost(duration_seconds: float) -> float:
    """Estimated USD cost to transcribe ``duration_seconds`` via AssemblyAI.

    Based on raw media duration, NOT VAD-derived speech duration. The spec
    documents this as an upper bound until the F3 cache + VAD sidecar
    land later.
    """
    return (duration_seconds / 60.0) * ASSEMBLYAI_RATE_PER_MINUTE_USD


def check(
    *,
    provider_name: str,
    budget: str,
    key_configured: bool,
    cost_usd: float,
    yes: bool,
    prompt: Callable[[str], bool],
    notify: Callable[[str], None],
) -> bool:
    """Run both gates and the confirmation flow.

    Returns ``True`` if the caller should proceed with the paid call,
    ``False`` if the user declined the confirmation prompt. Raises
    :class:`BudgetError` on either gate failure so the CLI can map both to
    exit code 2.

    ``prompt`` and ``notify`` are injected so tests can assert call counts
    and content without spinning up ``rich`` or stdin.
    """
    # Gate 1: key/endpoint configured?
    if not key_configured:
        raise BudgetError(
            f"{provider_name} key not configured. "
            "Add `ASSEMBLYAI_API_KEY=...` to `.env` (see `.env.example`)."
        )

    # Gate 2: budget allows paid?
    if budget == "free":
        raise BudgetError(
            f"{provider_name} is a paid provider "
            f"(${ASSEMBLYAI_RATE_PER_MINUTE_USD:.3f}/min). "
            "Current budget is `free`. Rerun with `--budget low` "
            "(or `--budget best`)."
        )

    # Both gates pass — surface the estimate.
    notify(f"Provider: {provider_name} · Estimated cost: ~${cost_usd:.2f}")

    # Soft cap: louder warning above the threshold, but ``--yes`` still
    # bypasses the prompt (consistent with smaller jobs).
    if cost_usd > SOFT_CAP_USD:
        notify(
            f"⚠️  Estimated cost ${cost_usd:.2f} exceeds soft cap "
            f"${SOFT_CAP_USD:.2f} — review before proceeding."
        )

    if yes:
        return True

    return prompt("Proceed? [y/N]")
