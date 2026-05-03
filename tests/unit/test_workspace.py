"""Tests for ``core/workspace.py`` — RunWorkspace context manager.

Covers cases 15-17 (happy path, keep_temp preserves, cleanup robust to
exceptions).
"""

from __future__ import annotations

import shutil

import pytest

from transcriber.core.workspace import RunWorkspace


def test_workspace_happy_path() -> None:
    """Case 15: dir created, child paths under root, cleanup runs on exit."""
    with RunWorkspace() as ws:
        assert ws.root.exists()
        assert ws.root.is_dir()
        child = ws.path("audio.wav")
        assert child.parent == ws.root
        # Workspace can write into the child path.
        child.write_text("x", encoding="utf-8")
        assert child.exists()
        captured_root = ws.root

    assert not captured_root.exists()


def test_workspace_keep_temp_preserves() -> None:
    """Case 16: keep=True leaves the dir on disk after __exit__."""
    ws = RunWorkspace(keep=True)
    captured_root = ws.root
    with ws:
        pass
    try:
        assert captured_root.exists()
    finally:
        shutil.rmtree(captured_root, ignore_errors=True)


def test_workspace_cleanup_on_exception() -> None:
    """Case 17: cleanup runs even when the body raises."""
    ws = RunWorkspace()
    captured_root = ws.root
    with pytest.raises(ValueError):
        with ws:
            raise ValueError("boom")
    assert not captured_root.exists()
