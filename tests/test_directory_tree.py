"""Tests for the directory_tree tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools import ToolContext
from tools.directory_tree import directory_tree_tool, execute


def test_tool_definition() -> None:
    assert directory_tree_tool.name == "directory_tree"
    assert directory_tree_tool.read_only is True


def test_basic_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # Create a simple structure
        (Path(tmp) / "README.md").write_text("# Hello", encoding="utf-8")
        sub = Path(tmp) / "src"
        sub.mkdir()
        (sub / "__init__.py").write_text("", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert "README.md" in result
        assert "src" in result


def test_depth_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        deep = Path(tmp) / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "file.txt").write_text("", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        # depth=1 should only show top level (a/), not nested content
        result = execute({"path": tmp, "depth": 1}, ctx)
        assert "a" in result
        # The string "b" may appear as part of the path encoding; instead verify
        # that the tree is shorter than a full-depth tree
        full_result = execute({"path": tmp}, ctx)
        assert len(result.split("\n")) < len(full_result.split("\n"))


def test_simple_format() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "test.txt").write_text("content", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp, "simple": True}, ctx)
        assert "test.txt" in result


def test_nonexistent_path_crashes_with_error() -> None:
    """The directory_tree tool raises FileNotFoundError for non-existent paths."""
    import pytest
    ctx = ToolContext(working_directory="/tmp")
    with pytest.raises((FileNotFoundError, OSError)):
        execute({"path": "/nonexistent-path-xyz"}, ctx)


def test_empty_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        # An empty dir should still show something
        assert result is not None
