"""Tests for the git_push tool."""

from __future__ import annotations

from src.tools import ToolContext
from src.tools.git_push import execute, git_push_tool


def test_tool_definition() -> None:
    assert git_push_tool.name == "git_push"
    assert git_push_tool.read_only is False


def test_execute_not_a_repo() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        result = execute({"branch": "main", "path": tmp}, ctx)
        assert "Error" in result or "not a git" in result.lower()
