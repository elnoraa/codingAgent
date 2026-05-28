"""Tests for the replace_in_files tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools import ToolContext
from tools.replace_in_files import replace_in_files_tool


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert replace_in_files_tool.name == "replace_in_files"
    assert replace_in_files_tool.read_only is False


def test_accepts_oldText() -> None:
    """Should work with camelCase 'oldText' key."""
    with tempfile.TemporaryDirectory() as tmp:
        filepath = str(Path(tmp) / "test.txt")
        Path(filepath).write_text("hello world", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        from tools.replace_in_files import execute

        result = execute({
            "path": tmp,
            "oldText": "hello",
            "newText": "hi",
        }, ctx)

        assert "Replacements:" in result and "1 applied" in result
        assert Path(filepath).read_text(encoding="utf-8") == "hi world"


def test_accepts_old_string() -> None:
    """Should work with snake_case 'old_string' key."""
    with tempfile.TemporaryDirectory() as tmp:
        filepath = str(Path(tmp) / "test.txt")
        Path(filepath).write_text("hello world", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        from tools.replace_in_files import execute

        result = execute({
            "path": tmp,
            "old_string": "hello",
            "new_string": "hi",
        }, ctx)

        assert "Replacements:" in result and "1 applied" in result
        assert Path(filepath).read_text(encoding="utf-8") == "hi world"


def test_missing_oldText_returns_error() -> None:
    """Should return error when both oldText and old_string are missing."""
    ctx = ToolContext(working_directory="/tmp")
    from tools.replace_in_files import execute

    result = execute({"newText": "y"}, ctx)
    assert 'missing required argument "oldText"' in result


def test_missing_newText_returns_error() -> None:
    """Should return error when both newText and new_string are missing."""
    ctx = ToolContext(working_directory="/tmp")
    from tools.replace_in_files import execute

    result = execute({"oldText": "x"}, ctx)
    assert 'missing required argument "newText"' in result
