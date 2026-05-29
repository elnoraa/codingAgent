"""Tests for the diff tool."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.diff_tool import diff_tool, execute


def _init_git_repo(path: str) -> None:
    """Initialize a minimal git repo in the given directory."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)


def test_tool_definition() -> None:
    assert diff_tool.name == "diff"
    assert diff_tool.read_only is True


def test_execute_not_in_git_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert "not inside a git repository" in result


def test_execute_no_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_git_repo(tmp)
        # Create a file and commit it
        test_file = Path(tmp) / "test.txt"
        test_file.write_text("hello", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp, capture_output=True)

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert "No changes" in result


def test_execute_with_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_git_repo(tmp)
        test_file = Path(tmp) / "test.txt"
        test_file.write_text("hello", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp, capture_output=True)

        # Make a change
        test_file.write_text("hello world", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert "hello world" in result
        assert "No changes" not in result


def test_execute_staged_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_git_repo(tmp)
        test_file = Path(tmp) / "test.txt"
        test_file.write_text("original", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp, capture_output=True)

        # Stage a change
        test_file.write_text("staged content", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp, "staged": True}, ctx)
        assert "staged content" in result


def test_execute_truncation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_git_repo(tmp)
        test_file = Path(tmp) / "test.txt"
        test_file.write_text("line1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp, capture_output=True)

        # Make many changes
        test_file.write_text("\n".join(f"line{i}" for i in range(100)), encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp, "maxLines": 5}, ctx)
        assert "more lines" in result
