"""Tests for the git_revert tool."""

from __future__ import annotations

from tools import ToolContext
from tools.git_revert import git_revert_tool, execute


def test_tool_definition() -> None:
    assert git_revert_tool.name == "git_revert"
    assert git_revert_tool.read_only is False
