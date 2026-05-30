"""Tests for the git_revert tool."""

from __future__ import annotations

from src.tools.git_revert import git_revert_tool


def test_tool_definition() -> None:
    assert git_revert_tool.name == "git_revert"
    assert git_revert_tool.read_only is False
