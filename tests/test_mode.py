"""Tests for mode module."""

from __future__ import annotations

from src.mode import PLAN_MODE_SYSTEM_PROMPT


def test_plan_mode_prompt_exists() -> None:
    assert len(PLAN_MODE_SYSTEM_PROMPT) > 100


def test_plan_mode_prompt_instructions() -> None:
    assert "PLAN MODE" in PLAN_MODE_SYSTEM_PROMPT
    assert "read-only" in PLAN_MODE_SYSTEM_PROMPT
    assert "CANNOT" in PLAN_MODE_SYSTEM_PROMPT
