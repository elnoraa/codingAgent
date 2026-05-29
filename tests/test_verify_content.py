"""Tests for the verify_content tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.verify_content import verify_content_tool, execute


def test_tool_definition() -> None:
    assert verify_content_tool.name == "verify_content"
    assert verify_content_tool.read_only is True


def test_should_contain_found() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(f), "shouldContain": ["hello"]}, ctx)
        assert "PASS" in result


def test_should_contain_not_found() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(f), "shouldContain": ["goodbye"]}, ctx)
        assert "FAIL" in result


def test_should_not_contain_not_found() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(f), "shouldNotContain": ["goodbye"]}, ctx)
        assert "PASS" in result


def test_should_not_contain_found() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.txt"
        f.write_text("hello world secret", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(f), "shouldNotContain": ["secret"]}, ctx)
        assert "FAIL" in result


def test_regex_matching() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.txt"
        f.write_text("error: something broke at line 42", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({
            "path": str(f),
            "shouldContain": [r"error:.*line \d+"],
            "regex": True,
        }, ctx)
        assert "PASS" in result


def test_file_not_found() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"path": "/nonexistent/file.txt", "shouldContain": ["x"]}, ctx)
    assert "Error" in result or "not found" in result.lower()


def test_empty_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "empty.txt"
        f.write_text("", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": str(f), "shouldContain": ["anything"]}, ctx)
        assert "FAIL" in result


def test_multiple_should_contain_all_must_match() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.txt"
        f.write_text("apple banana cherry", encoding="utf-8")
        ctx = ToolContext(working_directory=tmp)
        # All present
        result = execute({"path": str(f), "shouldContain": ["apple", "banana"]}, ctx)
        assert "PASS" in result
        # One missing
        result = execute({"path": str(f), "shouldContain": ["apple", "durian"]}, ctx)
        assert "FAIL" in result
