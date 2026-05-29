"""Tests for the restart_session tool."""

from __future__ import annotations

from src.tools import ToolContext
from src.tools.restart_session import execute, restart_session_tool


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert restart_session_tool.name == "restart_session"
    assert restart_session_tool.read_only is True


def test_execute_sets_restart_flag() -> None:
    """execute() should set restart_requested on the context."""
    ctx = ToolContext(working_directory="/tmp")
    assert ctx.restart_requested is False
    result = execute({}, ctx)
    assert ctx.restart_requested is True
    assert "restarted" in result.lower() or "reset" in result.lower()
