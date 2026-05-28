"""Tests for the edit_file tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools import ToolContext
from tools.edit_file import edit_file_tool


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert edit_file_tool.name == "edit_file"
    assert edit_file_tool.read_only is False


def test_accepts_oldText() -> None:
    """Should work with camelCase 'oldText' key."""
    with tempfile.TemporaryDirectory() as tmp:
        filepath = str(Path(tmp) / "test.txt")
        Path(filepath).write_text("hello world", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        from tools.edit_file import execute

        result = execute({
            "path": filepath,
            "oldText": "hello",
            "newText": "hi",
        }, ctx)

        assert "Applied edit" in result
        assert Path(filepath).read_text(encoding="utf-8") == "hi world"


def test_accepts_old_string() -> None:
    """Should work with snake_case 'old_string' key."""
    with tempfile.TemporaryDirectory() as tmp:
        filepath = str(Path(tmp) / "test.txt")
        Path(filepath).write_text("hello world", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        from tools.edit_file import execute

        result = execute({
            "path": filepath,
            "old_string": "hello",
            "new_string": "hi",
        }, ctx)

        assert "Applied edit" in result
        assert Path(filepath).read_text(encoding="utf-8") == "hi world"


def test_oldText_takes_precedence_over_old_string() -> None:
    """When both are provided, camelCase should win."""
    with tempfile.TemporaryDirectory() as tmp:
        filepath = str(Path(tmp) / "test.txt")
        Path(filepath).write_text("alpha beta", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        from tools.edit_file import execute

        result = execute({
            "path": filepath,
            "oldText": "alpha",
            "old_string": "beta",
            "newText": "gamma",
        }, ctx)

        assert "Applied edit" in result
        assert Path(filepath).read_text(encoding="utf-8") == "gamma beta"


def test_missing_path_returns_error() -> None:
    """Should return error when path is missing."""
    ctx = ToolContext(working_directory="/tmp")
    from tools.edit_file import execute

    result = execute({"oldText": "x", "newText": "y"}, ctx)
    assert 'missing required argument "path"' in result


def test_missing_oldText_returns_error() -> None:
    """Should return error when both oldText and old_string are missing."""
    ctx = ToolContext(working_directory="/tmp")
    from tools.edit_file import execute

    result = execute({"path": "/nonexistent/file.txt", "newText": "y"}, ctx)
    assert 'missing required argument "oldText"' in result


def test_missing_newText_returns_error() -> None:
    """Should return error when both newText and new_string are missing."""
    ctx = ToolContext(working_directory="/tmp")
    from tools.edit_file import execute

    result = execute({"path": "/nonexistent/file.txt", "oldText": "x"}, ctx)
    assert 'missing required argument "newText"' in result
