"""Tests for the config introspection tool."""

from __future__ import annotations

import pytest

from src.tools import ToolContext
from src.tools.config_tool import config_tool, execute


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert config_tool.name == "config"
    assert config_tool.read_only is True


def test_execute_returns_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config should show all set environment variables."""
    monkeypatch.setenv("CODING_AGENT_MODE", "code")
    monkeypatch.setenv("CODING_AGENT_MODEL", "test-model")
    monkeypatch.setenv("CODING_AGENT_MAX_TOKENS", "4096")
    monkeypatch.setenv("CODING_AGENT_TEMPERATURE", "0.7")
    monkeypatch.setenv("CODING_AGENT_PERSONA", "test persona")

    ctx = ToolContext(working_directory="/tmp")
    result = execute({}, ctx)

    assert "Working directory: /tmp" in result
    assert "Mode:              code" in result
    assert "Model:             test-model" in result
    assert "Max tokens:        4096" in result
    assert "Temperature:       0.7" in result
    assert "Custom persona:    test persona" in result


def test_execute_no_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without env vars, config should show 'unknown'."""
    monkeypatch.delenv("CODING_AGENT_MODE", raising=False)
    monkeypatch.delenv("CODING_AGENT_MODEL", raising=False)

    ctx = ToolContext(working_directory="/tmp")
    result = execute({}, ctx)
    assert "Mode:              unknown" in result
    assert "Model:             unknown" in result
