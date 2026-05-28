"""Tests for mode module."""

from __future__ import annotations

from src.mode import ASK_MODE_SYSTEM_PROMPT, PLAN_MODE_SYSTEM_PROMPT


def test_plan_mode_prompt_exists() -> None:
    assert len(PLAN_MODE_SYSTEM_PROMPT) > 100


def test_plan_mode_prompt_instructions() -> None:
    assert "PLAN MODE" in PLAN_MODE_SYSTEM_PROMPT
    assert "read-only" in PLAN_MODE_SYSTEM_PROMPT
    assert "CANNOT" in PLAN_MODE_SYSTEM_PROMPT


def test_ask_mode_prompt_exists() -> None:
    assert len(ASK_MODE_SYSTEM_PROMPT) > 100


def test_ask_mode_prompt_instructions() -> None:
    assert "ASK MODE" in ASK_MODE_SYSTEM_PROMPT
    assert "read-only" in ASK_MODE_SYSTEM_PROMPT
    assert "CANNOT" in ASK_MODE_SYSTEM_PROMPT
    assert "explain" in ASK_MODE_SYSTEM_PROMPT.lower()
    assert "plan" not in ASK_MODE_SYSTEM_PROMPT.lower() or "not in plan mode" in ASK_MODE_SYSTEM_PROMPT.lower()
