"""Tests for the run_tests tool."""

from __future__ import annotations

from tools import ToolContext
from tools.run_tests import run_tests_tool, execute


def test_tool_definition() -> None:
    assert run_tests_tool.name == "run_tests"
    assert run_tests_tool.read_only is False
