"""Tests for the syntax_check tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools import ToolContext
from tools.syntax_check import syntax_check_tool, execute


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert syntax_check_tool.name == "syntax_check"
    assert syntax_check_tool.read_only is True


def test_execute_missing_path() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({}, ctx)
    assert "Error" in result
    assert "path" in result.lower()


def test_execute_path_not_found() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"path": "/nonexistent/path/file.py"}, ctx)
    assert "Error" in result
    assert "not found" in result.lower()


def test_execute_single_file_valid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        py_file = Path(tmp) / "valid.py"
        py_file.write_text("x = 1\nprint(x)\n", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(py_file)}, ctx)
        assert "OK" in result
        assert str(py_file) in result
        assert "1 passed" in result


def test_execute_single_file_invalid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        py_file = Path(tmp) / "invalid.py"
        py_file.write_text("def foo(:\n    pass\n", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(py_file)}, ctx)
        assert "ERR" in result
        assert str(py_file) in result
        assert "1 failed" in result


def test_execute_non_py_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        txt_file = Path(tmp) / "readme.txt"
        txt_file.write_text("hello", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(txt_file)}, ctx)
        assert "Error" in result
        assert "not a Python" in result


def test_execute_directory_recursive() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # Create valid and invalid files
        (Path(tmp) / "good.py").write_text("x = 1\n", encoding="utf-8")
        (Path(tmp) / "bad.py").write_text("def foo(:\n", encoding="utf-8")
        # Create a subdirectory
        sub = Path(tmp) / "subdir"
        sub.mkdir()
        (sub / "also_good.py").write_text("y = 2\n", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert "2 passed" in result  # good.py + also_good.py
        assert "1 failed" in result  # bad.py


def test_execute_skips_ignored_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "good.py").write_text("x = 1\n", encoding="utf-8")
        # These should be skipped
        ignored = Path(tmp) / "__pycache__"
        ignored.mkdir()
        (ignored / "cached.py").write_text("bad syntax(", encoding="utf-8")
        git = Path(tmp) / ".git"
        git.mkdir()
        (git / "hooks.py").write_text("bad syntax(", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert "1 passed" in result
        assert "0 failed" in result or "1 failed" not in result


def test_execute_empty_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert "No Python files found" in result
