"""Tests for the docker tool."""

from __future__ import annotations

from tools import ToolContext
from tools.docker_tool import docker_tool, execute


def test_tool_definition() -> None:
    assert docker_tool.name == "docker"
    assert docker_tool.read_only is False
