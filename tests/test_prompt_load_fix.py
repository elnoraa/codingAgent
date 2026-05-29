"""Tests for /prompt load fix and roadmap behavior fix.

These tests validate:
1. Built-in prompts contain expected content (loading works correctly)
2. coding-agent.md contains the anti-roadmap rule
3. PLAN_MODE_SYSTEM_PROMPT contains the anti-roadmap instruction

If any of these tests fail, it means a fix was regressed.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.prompts import BUILTIN_PROMPTS, load_prompt
from src.mode import PLAN_MODE_SYSTEM_PROMPT


# ── Tests for Bug 1: /prompt load ──────────────────────────────────────


def test_load_builtin_prompt_returns_full_content() -> None:
    """Loading a built-in prompt should return its full template content.

    If this fails, the prompt loading mechanism is broken, which means
    /prompt load cannot function at all.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        prompt = load_prompt("fix-bug", tmpdir)
        assert prompt is not None
        assert "root cause" in prompt.content
        assert "Identify" in prompt.content
        assert len(prompt.content) > 50


def test_load_all_builtin_prompts_succeed() -> None:
    """Every built-in prompt should be loadable by name.

    If this fails, one or more built-in prompts are broken.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in BUILTIN_PROMPTS:
            prompt = load_prompt(name, tmpdir)
            assert prompt is not None, f"Built-in prompt '{name}' failed to load"
            assert prompt.content, f"Built-in prompt '{name}' has empty content"


def test_load_nonexistent_prompt_returns_none() -> None:
    """Loading a prompt that doesn't exist should return None.

    /prompt load depends on this to show a 'not found' message.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_prompt("nonexistent-prompt-xyz", tmpdir)
        assert result is None


def test_custom_prompt_overrides_builtin() -> None:
    """A custom prompt with the same name as a built-in should take priority.

    /prompt load should prefer custom prompts over built-in ones.
    """
    from src.prompts import save_prompt

    with tempfile.TemporaryDirectory() as tmpdir:
        save_prompt("fix-bug", "Custom fix-bug instructions", tmpdir)
        loaded = load_prompt("fix-bug", tmpdir)
        assert loaded is not None
        assert loaded.content == "Custom fix-bug instructions"
        assert loaded.is_builtin is False


# ── Tests for Bug 2: Roadmap behavior ─────────────────────────────────


def test_coding_agent_md_contains_no_roadmap_rule() -> None:
    """coding-agent.md must contain a rule forbidding aggregate roadmap plans.

    If this fails, someone removed the anti-roadmap rule from coding-agent.md,
    which means the agent may start creating roadmap documents again.
    """
    repo_root = Path(__file__).resolve().parent.parent
    coding_agent_md = repo_root / "coding-agent.md"

    assert coding_agent_md.is_file(), f"coding-agent.md not found at {coding_agent_md}"

    content = coding_agent_md.read_text(encoding="utf-8")

    assert "Do NOT create aggregate" in content, (
        "Missing anti-roadmap rule in coding-agent.md. "
        "Expected 'Do NOT create aggregate' in the Plan Naming Convention section."
    )
    assert "individual plan file" in content or "one plan per feature" in content, (
        "Missing 'individual plan' requirement in coding-agent.md."
    )


def test_plan_mode_prompt_forbids_roadmaps() -> None:
    """PLAN_MODE_SYSTEM_PROMPT must instruct the agent to avoid roadmaps.

    If this fails, someone removed the anti-roadmap instruction from
    PLAN_MODE_SYSTEM_PROMPT in src/mode.py.
    """
    assert "Do not create aggregate" in PLAN_MODE_SYSTEM_PROMPT or "one plan per feature" in PLAN_MODE_SYSTEM_PROMPT, (
        "Missing anti-roadmap instruction in PLAN_MODE_SYSTEM_PROMPT. "
        "Expected 'Do not create aggregate' or 'one plan per feature'."
    )
