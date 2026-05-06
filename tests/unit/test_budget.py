"""Tests for ``core/budget.py`` — two-gate spend check + soft cap.

Covers cases 10-14 (Gate 1 fail, Gate 2 fail, prompt called/skipped,
soft cap warning).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from transcriber.core.budget import (
    SOFT_CAP_USD,
    BudgetError,
    check,
    estimate_assemblyai_cost,
)


def _noop_prompt(_msg: str) -> bool:
    return False


def _capture_prompt() -> tuple[list[str], Callable[[str], bool]]:
    calls: list[str] = []

    def prompt(msg: str) -> bool:
        calls.append(msg)
        return True

    return calls, prompt


def _capture_notify() -> tuple[list[str], Callable[[str], None]]:
    msgs: list[str] = []

    def notify(msg: str) -> None:
        msgs.append(msg)

    return msgs, notify


def test_estimate_cost_one_minute_with_diarization() -> None:
    """Default --speakers (diarization on): U3P + Speaker Diarization.

    Per empirical AssemblyAI billing data verified across two
    independent days (2026-05-03: 132m 43s = $0.508747; 2026-05-05:
    63m = $0.2415), the per-minute math is:
      Universal-3 Pro:     $0.003500/min
      Speaker Diarization: $0.000333/min
      Combined:            $0.003833/min
    """
    assert estimate_assemblyai_cost(60.0, diarize=True) == pytest.approx(
        0.003833, abs=1e-5
    )


def test_estimate_cost_ten_minutes_with_diarization() -> None:
    assert estimate_assemblyai_cost(600.0, diarize=True) == pytest.approx(
        0.03833, abs=1e-4
    )


def test_estimate_cost_no_diarization_drops_speaker_addon() -> None:
    """--no-speakers drops the diarization charge; only U3P billed."""
    assert estimate_assemblyai_cost(60.0, diarize=False) == pytest.approx(
        0.0035, abs=1e-5
    )


def test_estimate_cost_matches_real_pr17_run() -> None:
    """Lock the rate against the empirical PR #17 manual run:
    63 min audio, diarization on → exactly $0.2415 from the AssemblyAI
    Cost dashboard. If a future rate change drops this assertion,
    update the constants and re-verify against fresh dashboard data."""
    assert estimate_assemblyai_cost(63 * 60.0, diarize=True) == pytest.approx(
        0.2415, abs=0.005
    )


def test_gate1_fails_when_key_missing() -> None:
    """Case 10: no key configured → Gate 1 fails with a clear error."""
    _, notify = _capture_notify()
    with pytest.raises(BudgetError) as exc:
        check(
            provider_name="AssemblyAI",
            budget="low",
            key_configured=False,
            cost_usd=1.0,
            yes=True,
            prompt=_noop_prompt,
            notify=notify,
        )
    assert "ASSEMBLYAI_API_KEY" in str(exc.value)


def test_gate2_fails_with_free_budget_even_when_key_set() -> None:
    """Case 11: --budget free → Gate 2 fails even when key is configured."""
    _, notify = _capture_notify()
    with pytest.raises(BudgetError) as exc:
        check(
            provider_name="AssemblyAI",
            budget="free",
            key_configured=True,
            cost_usd=1.0,
            yes=True,
            prompt=_noop_prompt,
            notify=notify,
        )
    assert "paid provider" in str(exc.value)
    assert "free" in str(exc.value)


def test_both_gates_pass_prompt_called_when_not_yes() -> None:
    """Case 12: both gates pass + yes=False → prompt called once."""
    calls, prompt = _capture_prompt()
    _, notify = _capture_notify()

    proceed = check(
        provider_name="AssemblyAI",
        budget="low",
        key_configured=True,
        cost_usd=0.50,
        yes=False,
        prompt=prompt,
        notify=notify,
    )
    assert proceed is True
    assert len(calls) == 1


def test_both_gates_pass_prompt_skipped_when_yes() -> None:
    """Case 13: both pass + yes=True → prompt NOT called."""
    calls, prompt = _capture_prompt()
    _, notify = _capture_notify()

    proceed = check(
        provider_name="AssemblyAI",
        budget="low",
        key_configured=True,
        cost_usd=0.50,
        yes=True,
        prompt=prompt,
        notify=notify,
    )
    assert proceed is True
    assert len(calls) == 0


def test_soft_cap_warning_above_threshold() -> None:
    """Case 14: cost > $5 → louder warning printed alongside the prompt flow."""
    msgs, notify = _capture_notify()
    check(
        provider_name="AssemblyAI",
        budget="low",
        key_configured=True,
        cost_usd=SOFT_CAP_USD + 0.01,
        yes=True,
        prompt=_noop_prompt,
        notify=notify,
    )
    assert any("exceeds soft cap" in m for m in msgs)


def test_soft_cap_silent_below_threshold() -> None:
    msgs, notify = _capture_notify()
    check(
        provider_name="AssemblyAI",
        budget="low",
        key_configured=True,
        cost_usd=SOFT_CAP_USD - 0.01,
        yes=True,
        prompt=_noop_prompt,
        notify=notify,
    )
    assert not any("exceeds soft cap" in m for m in msgs)


def test_unknown_budget_value_rejected_before_paid_authorization() -> None:
    """Defence-in-depth: even if a caller bypasses the CLI's Typer Enum
    and passes a free-form string, an unrecognised tier must NOT fall
    through to ``budget == "free"`` (which would silently authorise paid
    use). The check rejects unknown values explicitly with a useful
    error naming the allowed set."""
    _, notify = _capture_notify()
    with pytest.raises(BudgetError) as exc:
        check(
            provider_name="AssemblyAI",
            budget="paind",  # typo'd "paid"
            key_configured=True,
            cost_usd=1.0,
            yes=True,
            prompt=_noop_prompt,
            notify=notify,
        )
    assert "Unknown budget" in str(exc.value)
    assert "free" in str(exc.value) and "low" in str(exc.value) and "best" in str(exc.value)


def test_user_declines_returns_false() -> None:
    _, notify = _capture_notify()

    def deny(_msg: str) -> bool:
        return False

    proceed = check(
        provider_name="AssemblyAI",
        budget="low",
        key_configured=True,
        cost_usd=0.50,
        yes=False,
        prompt=deny,
        notify=notify,
    )
    assert proceed is False


def test_check_uses_cost_summary_override_when_set() -> None:
    """Slice 2: URL-passthrough sources (Drive) have no local duration to
    estimate against. They pass cost_summary=... to override the standard
    notify line. The soft-cap line is also silenced since there's no real
    cost number to compare. Both Gate 1 and Gate 2 still fire normally."""
    msgs, notify = _capture_notify()
    proceed = check(
        provider_name="AssemblyAI",
        budget="low",
        key_configured=True,
        cost_usd=999.0,  # would normally trigger soft cap
        yes=True,
        prompt=_noop_prompt,
        notify=notify,
        cost_summary="custom message — see dashboard",
    )
    assert proceed is True
    assert any("custom message — see dashboard" in m for m in msgs)
    # The standard "Estimated cost" line is replaced, not duplicated.
    assert not any("Estimated cost" in m for m in msgs)
    # The soft cap is silenced when cost_summary is set (no comparable
    # cost_usd to trigger it).
    assert not any("soft cap" in m for m in msgs)
