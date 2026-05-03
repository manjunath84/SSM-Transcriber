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


def test_estimate_cost_one_minute() -> None:
    assert estimate_assemblyai_cost(60.0) == pytest.approx(0.009)


def test_estimate_cost_ten_minutes() -> None:
    assert estimate_assemblyai_cost(600.0) == pytest.approx(0.09)


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
