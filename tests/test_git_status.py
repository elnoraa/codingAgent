"""Tests for the git_status tool."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.tools.git_status import git_status_tool, execute


def _init_repo(path: str) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)


def test_tool_definition() -> None:
    assert git_status_tool.name == "git_status"
    assert git_status_tool.read_only is True


def test_clean_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)
        p = Path(tmp) / "f.txt"
        p.write_text("initial", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp, capture_output=True)

        ctx = ToolContext(working_directory=tmp)
        result = execute({"path": tmp}, ctx)
        assert result is not None
