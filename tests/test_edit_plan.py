"""Tests for the edit_plan tool."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.tools.edit_plan import execute as edit_plan_execute
from src.tools import ToolContext


def _create_test_plan(pending_dir: Path, name: str, content: str) -> Path:
    """Create a test plan file with proper front-matter."""
    filepath = pending_dir / f"{name}.md"
    plan_content = f"""---
name: {name}
status: pending
created_at: 2026-01-01T00:00:00
---

{content}
"""
    filepath.write_text(plan_content, encoding="utf-8")
    return filepath


def test_edit_plan_updates_content() -> None:
    """Editing a plan should replace the body while preserving front-matter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plans_dir = Path(tmpdir) / "plans" / "pending"
        plans_dir.mkdir(parents=True, exist_ok=True)

        _create_test_plan(plans_dir, "01-test-plan", "Old content here")

        ctx = ToolContext(working_directory=tmpdir)
        result = edit_plan_execute({"name": "01-test-plan", "content": "New content here"}, ctx)

        assert "Plan updated" in result

        updated = (plans_dir / "01-test-plan.md").read_text(encoding="utf-8")
        assert "name: 01-test-plan" in updated  # front-matter preserved
        assert "status: pending" in updated       # front-matter preserved
        assert "created_at:" in updated            # front-matter preserved
        assert "Old content here" not in updated   # replaced
        assert "New content here" in updated       # new content present


def test_edit_plan_without_numeric_prefix() -> None:
    """Should match plans by name even without the leading number."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plans_dir = Path(tmpdir) / "plans" / "pending"
        plans_dir.mkdir(parents=True, exist_ok=True)

        _create_test_plan(plans_dir, "05-feat-my-feature", "Original body")

        ctx = ToolContext(working_directory=tmpdir)
        result = edit_plan_execute({"name": "feat-my-feature", "content": "Updated body"}, ctx)

        assert "Plan updated" in result
        updated = (plans_dir / "05-feat-my-feature.md").read_text(encoding="utf-8")
        assert "Updated body" in updated


def test_edit_plan_not_found() -> None:
    """Should return an error for non-existent plans."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)
        result = edit_plan_execute({"name": "nonexistent-plan", "content": "Irrelevant"}, ctx)
        assert "Error" in result
        assert "not found" in result


def test_edit_plan_missing_arguments() -> None:
    """Should return an error when required arguments are missing."""
    ctx = ToolContext(working_directory="/tmp")

    result_missing_name = edit_plan_execute({"content": "Some content"}, ctx)
    assert "Error" in result_missing_name
    assert "name" in result_missing_name

    result_missing_content = edit_plan_execute({"name": "test"}, ctx)
    assert "Error" in result_missing_content
    assert "content" in result_missing_content


def test_edit_plan_verifies_file_exists() -> None:
    """After writing, the tool should verify the file exists on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plans_dir = Path(tmpdir) / "plans" / "pending"
        plans_dir.mkdir(parents=True, exist_ok=True)

        _create_test_plan(plans_dir, "01-verify-test", "Original")

        ctx = ToolContext(working_directory=tmpdir)
        result = edit_plan_execute({"name": "01-verify-test", "content": "Updated"}, ctx)

        assert "Plan updated" in result
        filepath = plans_dir / "01-verify-test.md"
        assert filepath.is_file(), "File should exist after edit"


def test_edit_plan_no_front_matter() -> None:
    """If the plan has no YAML front-matter, the whole file is replaced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plans_dir = Path(tmpdir) / "plans" / "pending"
        plans_dir.mkdir(parents=True, exist_ok=True)

        filepath = plans_dir / "01-no-frontmatter.md"
        filepath.write_text("Just plain content", encoding="utf-8")

        ctx = ToolContext(working_directory=tmpdir)
        result = edit_plan_execute({"name": "01-no-frontmatter", "content": "New plain content"}, ctx)

        assert "Plan updated" in result
        updated = filepath.read_text(encoding="utf-8")
        assert updated.strip() == "New plain content"


def test_edit_plan_empty_content() -> None:
    """Empty or whitespace-only content should be rejected."""
    ctx = ToolContext(working_directory="/tmp")

    result_empty = edit_plan_execute({"name": "test", "content": ""}, ctx)
    assert "Error" in result_empty
    assert "content" in result_empty

    result_whitespace = edit_plan_execute({"name": "test", "content": "   "}, ctx)
    assert "Error" in result_whitespace


def test_edit_plan_empty_name() -> None:
    """Empty or whitespace-only name should be rejected."""
    ctx = ToolContext(working_directory="/tmp")

    result_empty = edit_plan_execute({"name": "", "content": "Some content"}, ctx)
    assert "Error" in result_empty

    result_whitespace = edit_plan_execute({"name": "   ", "content": "Some content"}, ctx)
    assert "Error" in result_whitespace


def test_edit_plan_does_not_create_new_file() -> None:
    """Editing a non-existent plan should NOT create the file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plans_dir = Path(tmpdir) / "plans" / "pending"
        plans_dir.mkdir(parents=True, exist_ok=True)

        ctx = ToolContext(working_directory=tmpdir)
        result = edit_plan_execute({"name": "brand-new-plan", "content": "Content"}, ctx)

        assert "Error" in result
        assert not (plans_dir / "brand-new-plan.md").exists(), (
            "edit_plan should not create new files — use write_plan for that"
        )


def test_edit_plan_preserves_complex_front_matter() -> None:
    """Front-matter with additional fields should be preserved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plans_dir = Path(tmpdir) / "plans" / "pending"
        plans_dir.mkdir(parents=True, exist_ok=True)

        filepath = plans_dir / "01-complex.md"
        filepath.write_text("""---
name: 01-complex
status: pending
created_at: 2026-01-01T00:00:00
author: test
priority: high
---

Original body
""", encoding="utf-8")

        ctx = ToolContext(working_directory=tmpdir)
        result = edit_plan_execute({"name": "01-complex", "content": "Updated body"}, ctx)

        assert "Plan updated" in result
        updated = filepath.read_text(encoding="utf-8")
        assert "author: test" in updated      # extra field preserved
        assert "priority: high" in updated     # extra field preserved
        assert "Original body" not in updated
        assert "Updated body" in updated
