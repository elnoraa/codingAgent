"""Tests for the API tool."""

from __future__ import annotations

from src.tools.api_tool import api_tool


def test_tool_definition() -> None:
    assert api_tool.name == "api"
    assert api_tool.read_only is False
