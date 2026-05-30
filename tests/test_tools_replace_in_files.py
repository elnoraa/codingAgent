"""Tests for the replace_in_files tool."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.tools import ToolContext
from src.tools.replace_in_files import replace_in_files_tool


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert replace_in_files_tool.name == "replace_in_files"
    assert replace_in_files_tool.read_only is False


def test_accepts_oldText() -> None:
    """Should work with camelCase 'oldText' key."""
    with tempfile.TemporaryDirectory() as tmp:
        filepath = str(Path(tmp) / "test.txt")
        Path(filepath).write_text("hello world", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        from src.tools.replace_in_files import execute

        result = execute(
            {
                "path": tmp,
                "oldText": "hello",
                "newText": "hi",
            },
            ctx,
        )

        assert "Replacements:" in result and "1 applied" in result
        assert Path(filepath).read_text(encoding="utf-8") == "hi world"


def test_accepts_old_string() -> None:
    """Should work with snake_case 'old_string' key."""
    with tempfile.TemporaryDirectory() as tmp:
        filepath = str(Path(tmp) / "test.txt")
        Path(filepath).write_text("hello world", encoding="utf-8")

        ctx = ToolContext(working_directory=tmp)
        from src.tools.replace_in_files import execute

        result = execute(
            {
                "path": tmp,
                "old_string": "hello",
                "new_string": "hi",
            },
            ctx,
        )

        assert "Replacements:" in result and "1 applied" in result
        assert Path(filepath).read_text(encoding="utf-8") == "hi world"


def test_missing_oldText_returns_error() -> None:
    """Should return error when both oldText and old_string are missing."""
    ctx = ToolContext(working_directory="/tmp")
    from src.tools.replace_in_files import execute

    result = execute({"newText": "y"}, ctx)
    assert 'missing required argument "oldText"' in result


def test_missing_newText_returns_error() -> None:
    """Should return error when both newText and new_string are missing."""
    ctx = ToolContext(working_directory="/tmp")
    from src.tools.replace_in_files import execute

    result = execute({"oldText": "x"}, ctx)
    assert 'missing required argument "newText"' in result


def test_replaces_rejects_symlink_escape(tmp_path: Path) -> None:
    """replace_in_files should skip symlinks pointing outside working dir."""

    outside_file = tmp_path / ".." / "outside.txt"
    outside_file = outside_file.resolve()
    outside_file.parent.mkdir(parents=True, exist_ok=True)
    outside_file.write_text("test content", encoding="utf-8")

    try:
        os.symlink(str(outside_file), str(tmp_path / "escape.txt"))
    except OSError, PermissionError:
        pytest.skip("Cannot create symlinks on this system")

    # Create a real file inside the working dir
    real_file = tmp_path / "real.txt"
    real_file.write_text("test content real", encoding="utf-8")

    ctx = ToolContext(working_directory=str(tmp_path))
    from src.tools.replace_in_files import execute

    result = execute(
        {
            "oldText": "test",
            "newText": "replaced",
            "path": str(tmp_path),
            "maxReplacements": 10,
        },
        ctx,
    )

    # The real file should have been modified
    assert "1 applied" in result or "2 applied" in result or "skipped" in result.lower()
    # The outside file should NOT have been modified
    assert outside_file.read_text(encoding="utf-8") == "test content"
