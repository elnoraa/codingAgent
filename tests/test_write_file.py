"""Tests for the write_file tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.write_file import execute, write_file_tool


def test_tool_definition() -> None:
    assert write_file_tool.name == "write_file"
    assert write_file_tool.read_only is False


def test_execute_creates_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        filepath = str(Path(tmp) / "new_file.txt")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": filepath, "content": "hello world"}, ctx)
        assert "Wrote" in result or "bytes" in result
        assert Path(filepath).exists()
        assert Path(filepath).read_text(encoding="utf-8") == "hello world"


def test_execute_creates_directories() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        filepath = str(Path(tmp) / "sub" / "dir" / "file.txt")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": filepath, "content": "nested"}, ctx)
        assert Path(filepath).exists()
        assert Path(filepath).read_text(encoding="utf-8") == "nested"
