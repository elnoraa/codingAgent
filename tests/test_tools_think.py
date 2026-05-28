"""Tests for the think tool."""

from __future__ import annotations

from tools import ToolContext
from tools.think_tool import execute, think_tool


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert think_tool.name == "think"
    assert think_tool.read_only is True


def test_execute_returns_thinking() -> None:
    """execute() should return 'Thinking...'."""
    ctx = ToolContext(working_directory="/tmp")
    result = execute({}, ctx)
    assert result == "Thinking..."


def test_execute_ignores_args() -> None:
    """think tool should work with any args."""
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"random": "data", "foo": "bar"}, ctx)
    assert result == "Thinking..."
