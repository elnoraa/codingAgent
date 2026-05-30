"""Tests for the grep tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.grep_tool import execute, grep_tool


def test_tool_definition() -> None:
    assert grep_tool.name == "grep"
    assert grep_tool.read_only is True


def test_execute_finds_matches() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.py"
        f.write_text("def hello():\n    pass\n", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"pattern": "hello", "path": tmp}, ctx)
        assert "hello" in result
        assert "test.py" in result


def test_execute_no_matches() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        result = execute({"pattern": "nonexistent_pattern_xyz", "path": tmp}, ctx)
        assert "No matches" in result
