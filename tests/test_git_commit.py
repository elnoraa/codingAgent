"""Tests for the git_commit tool."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.git_commit import execute, git_commit_tool


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
