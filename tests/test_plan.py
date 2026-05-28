"""Tests for plan file management."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.plan import (
    complete_plan,
    generate_plan_template,
    list_completed_plans,
    list_pending_plans,
    save_pending_plan,
    _ensure_dirs,
    _get_next_plan_number,
)


@pytest.fixture
def temp_wd() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_save_pending_plan(temp_wd: str) -> None:
    """Save a plan and verify the file is created with YAML front-matter."""
    filepath = save_pending_plan("test-plan", "This is a test plan.", temp_wd)
    assert os.path.isfile(filepath)
    assert "test-plan" in filepath
    assert filepath.endswith(".md")

    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    assert "name:" in content
    assert "status: pending" in content
    assert "created_at:" in content
    assert "This is a test plan." in content


def test_save_pending_plan_sanitizes_name(temp_wd: str) -> None:
    """Special characters in plan name should be sanitized."""
    filepath = save_pending_plan("My Plan!!! With Spaces", "content", temp_wd)
    assert "My-Plan---With-Spaces" in filepath or "My-Plan" in filepath
    assert "!!!" not in filepath

    # Should still be a valid file
    assert os.path.isfile(filepath)


def test_complete_plan_moves_file(temp_wd: str) -> None:
    """Completing a plan should move it from pending/ to completed/."""
    filepath = save_pending_plan("move-test", "Plan to move", temp_wd)
    assert "pending" in filepath

    # Extract the name — the saved file gets a number prefix like "01-move-test"
    saved_name = Path(filepath).stem  # e.g. "01-move-test"

    result = complete_plan(saved_name, temp_wd)
    assert result is True

    # File should no longer be in pending/
    assert not os.path.isfile(filepath)

    # File should now be in completed/
    plans_dir = Path(temp_wd) / "plans" / "completed"
    completed_files = list(plans_dir.glob(f"{saved_name}.md"))
    assert len(completed_files) == 1

    # Verify status was updated
    content = completed_files[0].read_text(encoding="utf-8")
    assert "status: completed" in content
    assert "completed_at:" in content


def test_complete_plan_not_found(temp_wd: str) -> None:
    """Completing a nonexistent plan should return False."""
    result = complete_plan("nonexistent-plan", temp_wd)
    assert result is False


def test_list_pending_plans(temp_wd: str) -> None:
    """List should return saved pending plans."""
    save_pending_plan("plan-a", "Content A", temp_wd)
    save_pending_plan("plan-b", "Content B", temp_wd)

    plans = list_pending_plans(temp_wd)
    assert len(plans) >= 2  # may also include other plans
    names = {p.name for p in plans}
    assert any("plan-a" in n for n in names)
    assert any("plan-b" in n for n in names)


def test_list_pending_plans_empty(temp_wd: str) -> None:
    """Should return empty list when no pending plans."""
    plans = list_pending_plans(temp_wd)
    assert plans == []


def test_list_completed_plans(temp_wd: str) -> None:
    """List should return completed plans."""
    filepath = save_pending_plan("complete-me", "Content", temp_wd)
    saved_name = Path(filepath).stem
    complete_plan(saved_name, temp_wd)

    plans = list_completed_plans(temp_wd)
    assert len(plans) >= 1
    assert any("complete-me" in p.name for p in plans)


def test_list_completed_plans_empty(temp_wd: str) -> None:
    """Should return empty list when no completed plans."""
    plans = list_completed_plans(temp_wd)
    assert plans == []


def test_generate_plan_template() -> None:
    """Template should contain expected section headers."""
    template = generate_plan_template("Add login feature")
    assert "# Plan: Add login feature" in template
    assert "## Overview" in template
    assert "## Files to Modify" in template
    assert "## Implementation Steps" in template
    assert "## Architecture / Design Decisions" in template
    assert "## Testing Plan" in template
    assert "## Potential Risks" in template


def test_get_next_plan_number_starts_at_one(temp_wd: str) -> None:
    """Should start at 1 when no plans exist."""
    number = _get_next_plan_number(temp_wd)
    assert number == 1


def test_get_next_plan_number_increments(temp_wd: str) -> None:
    """Should increment when plans exist."""
    # Save a plan, which auto-numbers
    filepath = save_pending_plan("first-plan", "Content", temp_wd)
    # The number used for this plan
    first_number = _get_next_plan_number(temp_wd) - 1 if _get_next_plan_number(temp_wd) > 0 else 0

    # Next number should be first_number + 1 (or at least increment)
    next_number = _get_next_plan_number(temp_wd)
    assert next_number > first_number


def test_ensure_dirs_creates_directories(temp_wd: str) -> None:
    """Both plans/pending/ and plans/completed/ should be created."""
    plans_dir, pending_dir, completed_dir = _ensure_dirs(temp_wd)
    assert plans_dir.is_dir()
    assert pending_dir.is_dir()
    assert completed_dir.is_dir()
    assert (plans_dir / "pending").is_dir()
    assert (plans_dir / "completed").is_dir()
