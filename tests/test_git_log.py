"""Tests for the git_log tool."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.git_log import execute, git_log_tool


def _init_repo(path: str) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)


def test_tool_definition() -> None:
    assert git_log_tool.name == "git_log"
    assert git_log_tool.read_only is True


def test_log_in_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)
        p = Path(tmp) / "f.txt"
        p.write_text("content", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "First commit"], cwd=tmp, capture_output=True)

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert "First commit" in result or "commit" in result.lower()
