"""Shared exception base for all transcriber-domain failures.

Java analogue: a single ``TranscriberException extends RuntimeException``
parent with subclasses for each failure mode. Catching the base lets a
future caller handle any domain failure uniformly (logging, metrics,
retry policy) without coupling to specific subclasses.

Subclasses partition the failure modes that map to CLI exit codes:

- :class:`transcriber.core.budget.BudgetError` → exit 2 (config)
- :class:`transcriber.providers.base.ProviderError` → exit 3 (provider)
- :class:`transcriber.core.audio.AudioExtractError` → exit 4 (local)
"""

from __future__ import annotations


class TranscriberError(Exception):
    """Base for all domain-specific exceptions raised by the transcriber.

    Inheriting from ``Exception`` (not ``RuntimeError``) signals these are
    business-domain conditions, not Python runtime bugs — the same
    distinction Java draws between checked/business exceptions and
    ``RuntimeException``.
    """
