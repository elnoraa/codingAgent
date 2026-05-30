"""Tests for the list_directory tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.list_directory import execute, list_directory_tool


def test_tool_definition() -> None:
    assert list_directory_tool.name == "list_directory"
    assert list_directory_tool.read_only is True


def test_execute_basic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "file1.txt").write_text("", encoding="utf-8")
        (Path(tmp) / "file2.txt").write_text("", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert "file1.txt" in result
        assert "file2.txt" in result


def test_execute_no_such_dir() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"path": "/nonexistent-dir-xyz"}, ctx)
    assert "Error" in result or "not found" in result.lower()
