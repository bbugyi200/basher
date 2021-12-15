"""Tests the basher project's CLI."""

from __future__ import annotations

from basher import main


def test_main() -> None:
    """Tests main() function."""
    assert main([""]) == 0
