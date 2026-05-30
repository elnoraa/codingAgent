"""Tests for the glob tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.glob_tool import execute, glob_tool


def test_tool_definition() -> None:
    assert glob_tool.name == "glob"
    assert glob_tool.read_only is True


def test_execute_finds_py_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a.py").write_text("", encoding="utf-8")
        (Path(tmp) / "b.py").write_text("", encoding="utf-8")
        (Path(tmp) / "readme.md").write_text("", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"pattern": "*.py", "path": tmp}, ctx)
        assert "a.py" in result
        assert "b.py" in result
        assert "readme.md" not in result


def test_execute_no_matches() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        result = execute({"pattern": "*.xyz", "path": tmp}, ctx)
        assert "No files found matching" in result


def test_execute_recursive_pattern() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / "subdir"
        sub.mkdir()
        (sub / "nested.py").write_text("", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"pattern": "**/*.py", "path": tmp}, ctx)
        assert "nested.py" in result
