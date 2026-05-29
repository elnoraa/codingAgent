"""Tests for the rename_file tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.rename_file import rename_file_tool, execute


def test_tool_definition() -> None:
    assert rename_file_tool.name == "rename_file"
    assert rename_file_tool.read_only is False


def test_rename_file_basic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "old.txt"
        source.write_text("content", encoding="utf-8")
        dest = str(Path(tmp) / "new.txt")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"source": str(source), "destination": dest}, ctx)
        assert "old.txt" in result
        assert "new.txt" in result or str(dest) in result
        assert not source.exists()
        assert Path(dest).exists()


def test_rename_missing_source() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        result = execute({
            "source": str(Path(tmp) / "nonexistent.txt"),
            "destination": str(Path(tmp) / "new.txt"),
        }, ctx)
        assert "Error" in result or "not found" in result.lower()


def test_rename_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "old_dir"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("hello", encoding="utf-8")

        dest = str(Path(tmp) / "new_dir")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"source": str(source_dir), "destination": dest}, ctx)
        assert "old_dir" in result
        assert "new_dir" in result or str(dest) in result
        assert not source_dir.exists()
        assert Path(dest).exists()
        assert (Path(dest) / "file.txt").exists()
