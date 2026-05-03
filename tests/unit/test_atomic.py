"""Tests for ``core/atomic.py`` — atomic write + collision resolution.

Covers cases 18 and 19 (success path / failure-leaves-original-intact)
plus the collision-suffix policy used by the CLI.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from transcriber.core.atomic import resolve_collision, write_text_atomic


def test_write_text_atomic_happy_path(tmp_path: Path) -> None:
    target = tmp_path / "out" / "transcript.md"
    write_text_atomic(target, "hello world")
    assert target.read_text(encoding="utf-8") == "hello world"
    assert not (target.parent / "transcript.md.tmp").exists()


def test_write_text_atomic_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "out.md"
    write_text_atomic(target, "x")
    assert target.exists()


def test_write_text_atomic_failure_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Case 19: a failed ``os.replace`` leaves the original intact and
    cleans up the partial ``.tmp``."""
    target = tmp_path / "out.md"
    target.write_text("ORIGINAL", encoding="utf-8")

    def boom(_src: object, _dst: object) -> None:
        raise OSError("simulated mid-rename failure")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError):
        write_text_atomic(target, "NEW")

    assert target.read_text(encoding="utf-8") == "ORIGINAL"
    assert not (tmp_path / "out.md.tmp").exists()


def test_resolve_collision_returns_path_when_free(tmp_path: Path) -> None:
    p = tmp_path / "fresh.md"
    assert resolve_collision(p) == p


def test_resolve_collision_increments_suffix(tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("", encoding="utf-8")

    candidate_2 = resolve_collision(p)
    assert candidate_2 == tmp_path / "a-2.md"

    (tmp_path / "a-2.md").write_text("", encoding="utf-8")
    assert resolve_collision(p) == tmp_path / "a-3.md"
