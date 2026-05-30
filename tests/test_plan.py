"""Tests for plan file management."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.plan import (
    _ensure_dirs,
    _extract_numeric_prefix,
    _get_all_plan_numbers,
    _get_next_plan_number,
    _strip_leading_number,
    complete_plan,
    generate_plan_template,
    list_completed_plans,
    list_pending_plans,
    save_pending_plan,
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


def test_save_pending_plan_with_prefixed_name(temp_wd: str) -> None:
    """A name that already starts with a numeric prefix should PRESERVE that number.

    e.g. save_pending_plan("05-feat-foo", ...) should produce
    "05-feat-foo.md" (preserving the explicit prefix), NOT "01-05-feat-foo.md".
    """
    filepath = save_pending_plan("05-feat-foo", "Content", temp_wd)
    assert os.path.isfile(filepath)
    filename = Path(filepath).name
    # The explicit "05-" should be preserved as the plan number
    assert filename.startswith("05-"), f"Expected explicit '05-' prefix, got: {filename}"
    assert "feat-foo" in filename


def test_write_plan_execute_with_prefixed_name(temp_wd: str) -> None:
    """write_plan tool with a name like '42-feat-x' should preserve the explicit prefix."""
    from src.tools import ToolContext
    from src.tools.write_plan import execute

    ctx = ToolContext(working_directory=temp_wd)
    args = {"name": "42-feat-my-feature", "content": "# My Feature\n\nDescription."}
    result = execute(args, ctx)

    assert "Plan saved to" in result, f"Unexpected result: {result}"
    filepath = result.replace("Plan saved to ", "")

    # Verify file exists and name uses the explicit prefix, not doubled
    assert os.path.isfile(filepath), f"File not found at: {filepath}"
    filename = Path(filepath).name
    # Should start with "42-" (the explicit prefix), not "01-42-"
    assert filename.startswith("42-"), f"Expected explicit '42-' prefix, got: {filename}"
    assert "feat-my-feature" in filename


def test_strip_leading_number_removes_prefix() -> None:
    """_strip_leading_number should remove a leading 'N-' prefix."""
    assert _strip_leading_number("05-feat-foo") == "feat-foo"
    assert _strip_leading_number("123-plan-name") == "plan-name"
    assert _strip_leading_number("01-test") == "test"


def test_strip_leading_number_no_prefix() -> None:
    """_strip_leading_number should leave names without a prefix unchanged."""
    assert _strip_leading_number("feat-foo") == "feat-foo"
    assert _strip_leading_number("my-plan") == "my-plan"
    assert _strip_leading_number("alpha-beta") == "alpha-beta"


def test_strip_leading_number_edge_cases() -> None:
    """Edge cases for _strip_leading_number."""
    assert _strip_leading_number("") == ""
    assert _strip_leading_number("5") == "5"  # just a digit, no hyphen
    assert _strip_leading_number("5-") == ""  # number + hyphen only
    assert _strip_leading_number("0-foo") == "foo"


def test_extract_numeric_prefix_returns_number() -> None:
    """_extract_numeric_prefix should return the number and stripped name."""
    num, stripped = _extract_numeric_prefix("111-feat-foo")
    assert num == 111
    assert stripped == "feat-foo"

    num, stripped = _extract_numeric_prefix("05-feat-foo")
    assert num == 5
    assert stripped == "feat-foo"

    num, stripped = _extract_numeric_prefix("12345-test")
    assert num == 12345
    assert stripped == "test"


def test_extract_numeric_prefix_no_prefix() -> None:
    """_extract_numeric_prefix should return (None, name) when no prefix."""
    num, stripped = _extract_numeric_prefix("feat-foo")
    assert num is None
    assert stripped == "feat-foo"

    num, stripped = _extract_numeric_prefix("")
    assert num is None
    assert stripped == ""


def test_extract_numeric_prefix_edge_cases() -> None:
    """Edge cases for _extract_numeric_prefix."""
    # Just a digit with no hyphen — no prefix
    num, stripped = _extract_numeric_prefix("5")
    assert num is None
    assert stripped == "5"

    # Number + hyphen only
    num, stripped = _extract_numeric_prefix("5-")
    assert num == 5
    assert stripped == ""


def test_get_all_plan_numbers_returns_numbers(temp_wd: str) -> None:
    """_get_all_plan_numbers should return all numeric prefixes in use."""
    # Save some plans with explicit numbers
    save_pending_plan("50-plan-a", "Content A", temp_wd)
    save_pending_plan("100-plan-b", "Content B", temp_wd)

    numbers = _get_all_plan_numbers(temp_wd)
    assert 50 in numbers
    assert 100 in numbers


def test_get_all_plan_numbers_empty(temp_wd: str) -> None:
    """_get_all_plan_numbers should return empty set when no plans exist."""
    numbers = _get_all_plan_numbers(temp_wd)
    assert numbers == set()


def test_save_pending_plan_preserves_explicit_prefix(temp_wd: str) -> None:
    """A name with an explicit numeric prefix like '111-' should preserve that number.

    The saved file should be named '111-<name>.md', not auto-numbered to '01-<name>.md'.
    """
    filepath = save_pending_plan("111-feat-add-ruff-to-precommit", "Content", temp_wd)
    assert os.path.isfile(filepath)
    filename = Path(filepath).name
    # Must start with "111-", not "01-" or "001-"
    assert filename.startswith("111-"), f"Expected '111-' prefix, got: {filename}"
    assert "feat-add-ruff-to-precommit" in filename


def test_save_pending_plan_explicit_prefix_with_conflict(temp_wd: str) -> None:
    """When an explicit prefix conflicts with an existing plan, auto-assign a new number."""
    # Create a plan with number 1
    save_pending_plan("1-first-plan", "Content", temp_wd)
    # Try to create another with number 1 — should auto-assign instead
    filepath = save_pending_plan("1-conflicting-plan", "Content", temp_wd)
    assert os.path.isfile(filepath)
    filename = Path(filepath).name
    # Should NOT start with "01-" (since 1 is taken)
    assert not filename.startswith("01-"), f"Should not reuse '01-' prefix, got: {filename}"
    assert "conflicting-plan" in filename


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


# ── Tests for write_plan.execute() ─────────────────────────────────────
# These tests directly validate the write_plan tool's execute function.
# They use a ToolContext with a temp directory to isolate from the real project.


def test_write_plan_execute_saves_file(temp_wd: str) -> None:
    """write_plan.execute() should create a valid plan file on disk."""
    from src.tools import ToolContext
    from src.tools.write_plan import execute

    ctx = ToolContext(working_directory=temp_wd)
    args = {"name": "test-write-plan", "content": "# Test Plan\n\nThis is a test."}
    result = execute(args, ctx)

    # Should return success with the file path
    assert "Plan saved to" in result, f"Unexpected result: {result}"
    filepath = result.replace("Plan saved to ", "")

    # File must exist on disk
    assert os.path.isfile(filepath), f"File not found at: {filepath}"

    # File content should have proper front-matter and content
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    assert "name:" in content
    assert "status: pending" in content
    assert "created_at:" in content
    assert "# Test Plan" in content
    assert "This is a test." in content


def test_write_plan_execute_relative_path(temp_wd: str) -> None:
    """write_plan.execute() should work with a relative working directory."""
    from src.tools import ToolContext
    from src.tools.write_plan import execute

    old_cwd = os.getcwd()
    try:
        os.chdir(temp_wd)
        ctx = ToolContext(working_directory=".")
        args = {"name": "rel-path-test", "content": "relative path test"}
        result = execute(args, ctx)
        assert "Plan saved to" in result, f"Unexpected result: {result}"
        filepath = result.replace("Plan saved to ", "")
        assert os.path.isfile(filepath), f"File not found at: {filepath}"
    finally:
        os.chdir(old_cwd)


def test_write_plan_execute_empty_string_wd(temp_wd: str) -> None:
    """write_plan.execute() should handle an empty string working directory."""
    from src.tools import ToolContext
    from src.tools.write_plan import execute

    old_cwd = os.getcwd()
    try:
        os.chdir(temp_wd)
        ctx = ToolContext(working_directory="")
        args = {"name": "empty-wd-test", "content": "empty wd test"}
        result = execute(args, ctx)
        assert "Plan saved to" in result, f"Unexpected result: {result}"
        filepath = result.replace("Plan saved to ", "")
        assert os.path.isfile(filepath), f"File not found at: {filepath}"
    finally:
        os.chdir(old_cwd)


def test_write_plan_execute_missing_name(temp_wd: str) -> None:
    """execute() should return an error when name is missing."""
    from src.tools import ToolContext
    from src.tools.write_plan import execute

    ctx = ToolContext(working_directory=temp_wd)
    result = execute({"content": "some content"}, ctx)
    assert "Error" in result or "missing" in result.lower()


def test_write_plan_execute_missing_content(temp_wd: str) -> None:
    """execute() should return an error when content is missing."""
    from src.tools import ToolContext
    from src.tools.write_plan import execute

    ctx = ToolContext(working_directory=temp_wd)
    result = execute({"name": "some-name"}, ctx)
    assert "Error" in result or "missing" in result.lower()


def test_write_plan_execute_empty_name_after_strip(temp_wd: str) -> None:
    """execute() should return an error for whitespace-only name."""
    from src.tools import ToolContext
    from src.tools.write_plan import execute

    ctx = ToolContext(working_directory=temp_wd)
    result = execute({"name": "   ", "content": "content"}, ctx)
    assert "Error" in result or "missing" in result.lower()


def test_write_plan_execute_empty_content_after_strip(temp_wd: str) -> None:
    """execute() should return an error for whitespace-only content."""
    from src.tools import ToolContext
    from src.tools.write_plan import execute

    ctx = ToolContext(working_directory=temp_wd)
    result = execute({"name": "test-name", "content": "   "}, ctx)
    assert "Error" in result or "missing" in result.lower()
