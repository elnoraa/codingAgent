"""Tests for desktop notifications."""
from __future__ import annotations

from src.notifications import should_notify


def test_should_notify_above_threshold() -> None:
    """Should notify if elapsed time is >= min_duration."""
    assert should_notify(10.0, 10) is True
    assert should_notify(15.0, 10) is True
    assert should_notify(100.0, 10) is True


def test_should_notify_below_threshold() -> None:
    """Should not notify if elapsed time is < min_duration."""
    assert should_notify(0.0, 10) is False
    assert should_notify(5.0, 10) is False
    assert should_notify(9.999, 10) is False


def test_should_notify_default_threshold() -> None:
    """Default threshold is 10 seconds."""
    assert should_notify(10.0) is True
    assert should_notify(9.0) is False


def test_should_notify_zero_threshold() -> None:
    """Zero threshold means always notify."""
    assert should_notify(0.0, 0) is True
    assert should_notify(0.1, 0) is True
