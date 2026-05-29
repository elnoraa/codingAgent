"""Tests for the environment tool."""

from __future__ import annotations

from src.tools import ToolContext
from src.tools.environment import execute, environment_tool


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert environment_tool.name == "environment"
    assert environment_tool.read_only is True


def test_execute_returns_platform_info() -> None:
    """Environment should show runtime information."""
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"packages": False}, ctx)
    assert "Runtime Environment:" in result
    assert "Python:" in result
    assert "Platform:" in result
    assert "OS:" in result
    assert "CWD:" in result


def test_execute_defaults_to_no_packages() -> None:
    """Calling without 'packages' should not show installed packages."""
    ctx = ToolContext(working_directory="/tmp")
    result = execute({}, ctx)
    assert "Runtime Environment:" in result
    assert "Installed Packages:" not in result
