"""Tests for the git_branch tool."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.git_branch import execute, git_branch_tool


def _init_repo(path: str) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
    p = Path(path) / "f.txt"
    p.write_text("initial", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True)


def test_tool_definition() -> None:
    assert git_branch_tool.name == "git_branch"
    assert git_branch_tool.read_only is False


def test_list_branches() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)
        ctx = ToolContext(working_directory=tmp)
        result = execute({"action": "list", "path": tmp}, ctx)
        assert "main" in result or "master" in result


def test_create_and_switch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)
        ctx = ToolContext(working_directory=tmp)
        result = execute({"action": "create", "name": "feature", "path": tmp}, ctx)
        assert "feature" in result or "created" in result.lower()
