"""Tests for custom tools via config."""
from __future__ import annotations

import json
import os
import tempfile

from src.custom_tools import load_custom_tools


def test_load_bash_tool() -> None:
    """Load a custom bash tool from config."""
    config = {
        "tools": [
            {
                "name": "greet",
                "description": "Greet someone",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"}
                    },
                },
                "handler": {
                    "type": "bash",
                    "command": "echo Hello, {{name}}!",
                },
            }
        ]
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "custom_tools.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f)

        tools = load_custom_tools(config_path, tmpdir)
        assert len(tools) == 1
        assert tools[0].name == "greet"
        assert tools[0].description == "Greet someone"


def test_load_multiple_tools() -> None:
    """Load multiple custom tools."""
    config = {
        "tools": [
            {
                "name": "tool1",
                "description": "First tool",
                "input_schema": {"type": "object", "properties": {}},
                "handler": {"type": "bash", "command": "echo first"},
            },
            {
                "name": "tool2",
                "description": "Second tool",
                "input_schema": {"type": "object", "properties": {}},
                "handler": {"type": "bash", "command": "echo second"},
            },
        ]
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "custom_tools.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f)

        tools = load_custom_tools(config_path, tmpdir)
        assert len(tools) == 2


def test_config_not_found() -> None:
    """No config file should result in empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tools = load_custom_tools("nonexistent.json", tmpdir)
        assert tools == []


def test_empty_config() -> None:
    """Empty config path should result in empty list."""
    tools = load_custom_tools(None, "/tmp")
    assert tools == []


def test_empty_tools_list() -> None:
    """Config with empty tools list should return empty list."""
    config = {"tools": []}
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "custom_tools.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f)

        tools = load_custom_tools(config_path, tmpdir)
        assert tools == []


def test_invalid_json_handled() -> None:
    """Invalid JSON should not crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "custom_tools.json")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("not valid json")

        tools = load_custom_tools(config_path, tmpdir)
        assert tools == []


def test_invalid_tool_definition_skipped() -> None:
    """Invalid tool definitions should be skipped."""
    config = {
        "tools": [
            {"description": "missing name"},
            {
                "name": "valid_tool",
                "description": "A valid tool",
                "input_schema": {"type": "object", "properties": {}},
                "handler": {"type": "bash", "command": "echo ok"},
            },
        ]
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "custom_tools.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f)

        tools = load_custom_tools(config_path, tmpdir)
        assert len(tools) == 1
        assert tools[0].name == "valid_tool"


# ── Template validation tests ─────────────────────────────────────────────────


class TestTemplateValidation:
    """Verify template value sanitization."""

    def test_bash_blocks_semicolon(self) -> None:
        """Semicolons in bash template values should be blocked."""
        from src.custom_tools import _validate_template_value
        error = _validate_template_value("hello; rm -rf /", "bash")
        assert error is not None

    def test_bash_blocks_backtick(self) -> None:
        """Backticks in bash template values should be blocked."""
        from src.custom_tools import _validate_template_value
        error = _validate_template_value("`rm -rf /`", "bash")
        assert error is not None

    def test_bash_blocks_flag_prefix(self) -> None:
        """Values starting with '-' should be blocked."""
        from src.custom_tools import _validate_template_value
        error = _validate_template_value("--force", "bash")
        assert error is not None

    def test_bash_allows_safe_values(self) -> None:
        """Safe alphanumeric values should pass validation."""
        from src.custom_tools import _validate_template_value
        assert _validate_template_value("hello", "bash") is None
        assert _validate_template_value("user_input_123", "bash") is None
        assert _validate_template_value("file-name.txt", "bash") is None

    def test_http_blocks_crlf(self) -> None:
        """CR/LF characters in HTTP template values should be blocked."""
        from src.custom_tools import _validate_template_value
        error = _validate_template_value("value\r\nInjected-Header: malicious", "http")
        assert error is not None

    def test_http_allows_safe_values(self) -> None:
        """Safe URL values should pass HTTP validation."""
        from src.custom_tools import _validate_template_value
        assert _validate_template_value("user123", "http") is None
        assert _validate_template_value("search+query", "http") is None
