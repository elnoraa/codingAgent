"""Tests for the python_tool (python REPL tool)."""

from __future__ import annotations

from src.tools.python_tool import python_tool


def test_tool_definition() -> None:
    assert python_tool.name == "python"
    assert python_tool.read_only is False
