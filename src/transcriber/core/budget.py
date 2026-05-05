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

from transcriber.errors import TranscriberError

logger = logging.getLogger(__name__)


# AssemblyAI rates per `model.units * unit-cost` shape from the AssemblyAI
# Cost dashboard. Verified empirically across two independent days
# (2026-05-03: 132m 43s of audio billed $0.508747; 2026-05-05: 63m audio
# billed $0.2415) — both yield the same per-minute math:
#   Universal-3 Pro:     $0.003500/min   (the speech-to-text base rate)
#   Speaker Diarization: $0.000333/min   (add-on, billed only when on)
#   Combined:            $0.003833/min
#
# These replace the prior ASSEMBLYAI_RATE_PER_MINUTE_USD = 0.009 constant
# from PR #12 which over-quoted by 2.35x. The bug was caught when the
# Slice 2 manual runbook compared the dashboard cost ($0.2415) against
# the CLI's pre-run estimate ($0.567) — see PR #17's explainer for the
# full cost-vs-estimate gap finding.
UNIVERSAL_3_PRO_RATE_PER_MINUTE_USD: float = 0.0035
SPEAKER_DIARIZATION_RATE_PER_MINUTE_USD: float = 0.000333

# Back-compat alias retained for any external callers (none in-tree); the
# combined rate matches the default --speakers (diarization on) flow.
ASSEMBLYAI_RATE_PER_MINUTE_USD: float = (
    UNIVERSAL_3_PRO_RATE_PER_MINUTE_USD + SPEAKER_DIARIZATION_RATE_PER_MINUTE_USD
)

# Above this estimate, ``check`` emits a louder warning. ``--yes`` still
# bypasses the confirmation prompt; the warning is informational, not a hard
# gate. The hard gates remain Gate 1 and Gate 2.
SOFT_CAP_USD: float = 5.0

# Budget tier names the CLI/config accept. Unknown values must NOT be
# treated as "paid authorized" — that would weaken the two-gate spend
# contract (``--budget typo -y`` would silently proceed). Defence-in-depth:
# the CLI ``--budget`` flag is also a Typer Enum so bad inputs fail at
# parse time; this allowlist is the second line of defence inside the
# gate function.
ALLOWED_BUDGETS: frozenset[str] = frozenset({"free", "low", "best"})


class BudgetError(TranscriberError):
    """Gate 1 or Gate 2 failed. CLI maps this to exit code 2 (config)."""


def estimate_assemblyai_cost(
    duration_seconds: float, *, diarize: bool = True
) -> float:
    """Estimated USD cost to transcribe ``duration_seconds`` via AssemblyAI.

    Based on raw media duration, NOT VAD-derived speech duration. The spec
    documents this as an upper bound until the F3 cache + VAD sidecar
    land later.

    ``diarize`` defaults to ``True`` because the CLI's default is
    diarization-on (``--no-speakers`` flips it off). Pass ``False`` to
    drop the Speaker Diarization add-on charge from the estimate so the
    user sees an accurate quote when they intend to disable diarization.
    """
    minutes = duration_seconds / 60.0
    cost = minutes * UNIVERSAL_3_PRO_RATE_PER_MINUTE_USD
    if diarize:
        cost += minutes * SPEAKER_DIARIZATION_RATE_PER_MINUTE_USD
    return cost


def check(
    *,
    provider_name: str,
    budget: str,
    key_configured: bool,
    cost_usd: float,
    yes: bool,
    prompt: Callable[[str], bool],
    notify: Callable[[str], None],
    cost_summary: str | None = None,
) -> bool:
    """Run both gates and the confirmation flow.

    Returns ``True`` if the caller should proceed with the paid call,
    ``False`` if the user declined the confirmation prompt. Raises
    :class:`BudgetError` on either gate failure so the CLI can map both to
    exit code 2.

    ``prompt`` and ``notify`` are injected so tests can assert call counts
    and content without spinning up ``rich`` or stdin.

    ``cost_summary``: when set, overrides the default per-minute
    cost-estimate line. URL-passthrough sources (Drive in Slice 2) pass a
    string explaining that the provider bills per-minute and exact cost
    shows in the dashboard, since we have no local duration to estimate
    against. The soft-cap line is also silenced when ``cost_summary`` is
    set (no real cost number to compare against). When ``None``, the
    default ``f"Provider: {provider_name} · Estimated cost: ~${cost_usd:.2f}"``
    line is used.
    """
    # Reject unknown budget tiers BEFORE the gate checks. An unrecognised
    # value like ``"typo"`` would otherwise fall through Gate 2's
    # ``budget == "free"`` check and silently authorise paid use.
    if budget not in ALLOWED_BUDGETS:
        raise BudgetError(
            f"Unknown budget {budget!r}; expected one of "
            f"{sorted(ALLOWED_BUDGETS)}."
        )

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

    # Both gates pass — surface the estimate (or the override).
    if cost_summary is not None:
        notify(cost_summary)
    else:
        notify(f"Provider: {provider_name} · Estimated cost: ~${cost_usd:.2f}")

    # Soft cap: only fires when we have a real cost number to compare.
    if cost_summary is None and cost_usd > SOFT_CAP_USD:
        notify(
            f"⚠️  Estimated cost ${cost_usd:.2f} exceeds soft cap "
            f"${SOFT_CAP_USD:.2f} — review before proceeding."
        )

    if yes:
        return True

    return prompt("Proceed? [y/N]")
