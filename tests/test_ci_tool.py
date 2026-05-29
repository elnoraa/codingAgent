"""Tests for the CI tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools import ToolContext
from tools.ci_tool import ci_tool, execute


def test_tool_definition() -> None:
    assert ci_tool.name == "ci"
    assert ci_tool.read_only is False


def test_no_ci_detected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        result = execute({"action": "detect", "path": tmp}, ctx)
        assert "No CI/CD configuration" in result or "no" in result.lower()
