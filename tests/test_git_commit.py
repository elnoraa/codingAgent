"""Tests for the git_commit tool."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from src.tools import ToolContext
from src.tools.git_commit import (
    _hooks_modified_files,
    _hooks_rejected_commit,
    execute,
    git_commit_tool,
)


def _init_repo(path: str) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)


def test_tool_definition() -> None:
    assert git_commit_tool.name == "git_commit"
    assert git_commit_tool.read_only is False


def test_commit_with_message() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)
        p = Path(tmp) / "f.txt"
        p.write_text("content", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)

        ctx = ToolContext(working_directory=tmp)
        result = execute({"message": "Add f.txt", "all": True, "path": tmp}, ctx)
        assert "committed" in result.lower() or "commit" in result.lower()


def test_nothing_to_commit_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)
        ctx = ToolContext(working_directory=tmp)
        with pytest.raises(ValueError, match="Nothing to commit"):
            execute({"message": "test", "path": tmp}, ctx)


def test_not_a_git_repo_raises_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        with pytest.raises(ValueError, match="not inside a git repository"):
            execute({"message": "test", "path": tmp}, ctx)


def test_hooks_modified_files_detection() -> None:
    assert _hooks_modified_files("Files were modified by this hook") is True
    assert _hooks_modified_files("ruff: reformatted file.py") is True
    assert _hooks_modified_files("all checks passed") is False
    assert _hooks_modified_files("") is False


def test_hooks_rejected_commit_detection() -> None:
    assert _hooks_rejected_commit("some hook(s) failed") is True
    assert _hooks_rejected_commit("Failed\nsome error") is True
    assert _hooks_rejected_commit("") is False
    assert _hooks_rejected_commit("all checks passed") is False
