"""Tests for the precommit tool."""

from __future__ import annotations

import tempfile

from src.tools import ToolContext
from src.tools.precommit_tool import execute, precommit_tool


def test_tool_definition() -> None:
    assert precommit_tool.name == "precommit"
    assert precommit_tool.read_only is False


def test_no_precommit_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = ToolContext(working_directory=tmp)
        result = execute({"action": "status", "path": tmp}, ctx)
        assert ".pre-commit-config" in result
