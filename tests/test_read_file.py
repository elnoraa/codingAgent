"""Tests for the read_file tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.read_file import read_file_tool, execute


def test_tool_definition() -> None:
    assert read_file_tool.name == "read_file"
    assert read_file_tool.read_only is True


def test_execute_file_not_found() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"path": "/nonexistent/file.txt"}, ctx)
    assert "Error" in result or "not found" in result.lower()


def test_execute_basic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(f)}, ctx)
        assert "hello world" in result


def test_execute_with_offset() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lines = "\n".join(f"line{i}" for i in range(10))
        f = Path(tmp) / "test.txt"
        f.write_text(lines, encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(f), "offset": 5}, ctx)
        assert "line5" in result
        assert "line0" not in result


def test_execute_with_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lines = "\n".join(f"line{i}" for i in range(10))
        f = Path(tmp) / "test.txt"
        f.write_text(lines, encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(f), "limit": 3}, ctx)
        assert "line0" in result
        assert "line1" in result
        assert "line2" in result
        assert "line5" not in result
