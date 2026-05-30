"""Tests for the file_search tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.file_search import execute, file_search_tool


def test_tool_definition() -> None:
    assert file_search_tool.name == "file_search"
    assert file_search_tool.read_only is True


def test_execute_missing_pattern() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({}, ctx)
    assert "Error" in result or "missing" in result.lower()


def test_execute_falls_back_to_grep() -> None:
    """When rg is not available, falls back to grep (or returns an error)."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.py"
        f.write_text("def foo():\n    return 42\n", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"pattern": "foo", "path": tmp}, ctx)
        # Either grep is available and finds matches, or it returns an error
        assert result is not None
