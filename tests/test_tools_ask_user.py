"""Tests for the ask_user tool."""

from __future__ import annotations

import pytest
from tools import ToolContext
from tools.ask_user import execute, ask_user_tool, AskUserException


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert ask_user_tool.name == "ask_user"
    assert ask_user_tool.interactive is True
    assert ask_user_tool.read_only is False


def test_execute_raises_exception() -> None:
    """execute() should raise AskUserException with the question."""
    ctx = ToolContext(working_directory="/tmp")
    with pytest.raises(AskUserException) as excinfo:
        execute({"question": "What is your name?"}, ctx)
    assert "What is your name?" in str(excinfo.value)


def test_execute_missing_question() -> None:
    """Missing question should return an error string."""
    ctx = ToolContext(working_directory="/tmp")
    result = execute({}, ctx)
    assert "missing required argument" in result


def test_execute_empty_question() -> None:
    """Empty question should return an error string."""
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"question": ""}, ctx)
    assert "missing required argument" in result
