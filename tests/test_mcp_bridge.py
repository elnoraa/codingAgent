"""Tests for the MCP Bridge module.

Uses mocking to avoid needing actual MCP server processes during tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_bridge import (
    MCPServerConfig,
    MCPBridge,
    _serialize_tool_result,
    parse_server_configs,
)
from tools import ToolContext


# ── Tests for parse_server_configs ────────────────────────────────────────────


class TestParseServerConfigs:
    def test_empty_list(self) -> None:
        assert parse_server_configs([]) == []

    def test_valid_stdio_config(self) -> None:
        raw = [
            {
                "name": "sqlite",
                "transport": "stdio",
                "command": "uvx",
                "args": ["mcp-server-sqlite", "--db-path", "./test.db"],
            }
        ]
        result = parse_server_configs(raw)
        assert len(result) == 1
        assert result[0].name == "sqlite"
        assert result[0].transport == "stdio"
        assert result[0].command == "uvx"
        assert result[0].args == ["mcp-server-sqlite", "--db-path", "./test.db"]

    def test_valid_sse_config(self) -> None:
        raw = [
            {
                "name": "github",
                "transport": "sse",
                "url": "https://api.github.com/mcp",
                "headers": {"Authorization": "Bearer token123"},
            }
        ]
        result = parse_server_configs(raw)
        assert len(result) == 1
        assert result[0].name == "github"
        assert result[0].transport == "sse"
        assert result[0].url == "https://api.github.com/mcp"
        assert result[0].headers == {"Authorization": "Bearer token123"}

    def test_skips_empty_name(self) -> None:
        raw: list[dict[str, object]] = [{"name": "", "transport": "stdio", "command": "echo"}]
        assert parse_server_configs(raw) == []

    def test_skips_unknown_transport(self) -> None:
        raw: list[dict[str, object]] = [{"name": "test", "transport": "websocket", "command": "echo"}]
        assert parse_server_configs(raw) == []

    def test_skips_stdio_missing_command(self) -> None:
        raw: list[dict[str, object]] = [{"name": "test", "transport": "stdio"}]
        assert parse_server_configs(raw) == []

    def test_skips_sse_missing_url(self) -> None:
        raw: list[dict[str, object]] = [{"name": "test", "transport": "sse"}]
        assert parse_server_configs(raw) == []

    def test_mixed_valid_and_invalid(self) -> None:
        raw: list[dict[str, object]] = [
            {"name": "valid", "transport": "stdio", "command": "echo", "args": ["hello"]},
            {"name": "", "transport": "stdio", "command": "echo"},
            {"name": "invalid-transport", "transport": "http"},
        ]
        result = parse_server_configs(raw)
        assert len(result) == 1
        assert result[0].name == "valid"


# ── Tests for _serialize_tool_result ──────────────────────────────────────────


class FakeTextContent:
    """Fake MCP TextContent for testing."""
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text
        self.mimeType: str | None = None


class FakeImageContent:
    """Fake MCP ImageContent for testing."""
    def __init__(self, data: str, mime_type: str | None = None) -> None:
        self.type = "image"
        self.data = data
        self.mimeType = mime_type


class FakeEmbeddedResource:
    """Fake MCP EmbeddedResource for testing."""
    def __init__(self, uri: str) -> None:
        self.type = "resource"
        self.resource = FakeResource(uri)


class FakeResource:
    def __init__(self, uri: str) -> None:
        self.uri = uri


class FakeCallToolResult:
    """Fake MCP CallToolResult for testing."""
    def __init__(self, content: list[Any], is_error: bool = False) -> None:
        self.content = content
        self.isError = is_error


class TestSerializeToolResult:
    def test_text_content(self) -> None:
        result: Any = FakeCallToolResult([FakeTextContent("hello world")])
        assert _serialize_tool_result(result) == "hello world"

    def test_multiple_text_blocks(self) -> None:
        result: Any = FakeCallToolResult([
            FakeTextContent("line1"),
            FakeTextContent("line2"),
        ])
        assert _serialize_tool_result(result) == "line1\nline2"

    def test_image_content(self) -> None:
        result: Any = FakeCallToolResult([FakeImageContent("base64data", "image/png")])
        assert "Image: image/png" in _serialize_tool_result(result)

    def test_embedded_resource(self) -> None:
        result: Any = FakeCallToolResult([FakeEmbeddedResource("file:///test.txt")])
        assert "Embedded resource" in _serialize_tool_result(result)

    def test_error_result(self) -> None:
        result: Any = FakeCallToolResult([FakeTextContent("something went wrong")], is_error=True)
        assert _serialize_tool_result(result) == "Error: something went wrong"

    def test_empty_content(self) -> None:
        result: Any = FakeCallToolResult([])
        assert _serialize_tool_result(result) == ""


# ── Tests for MCPServerConfig dataclass ───────────────────────────────────────


class TestMCPServerConfig:
    def test_stdio_defaults(self) -> None:
        cfg = MCPServerConfig(name="test", transport="stdio", command="echo")
        assert cfg.name == "test"
        assert cfg.transport == "stdio"
        assert cfg.command == "echo"
        assert cfg.args is None
        assert cfg.env is None
        assert cfg.url is None
        assert cfg.headers is None

    def test_sse_defaults(self) -> None:
        cfg = MCPServerConfig(name="test", transport="sse", url="https://example.com/mcp")
        assert cfg.name == "test"
        assert cfg.transport == "sse"
        assert cfg.url == "https://example.com/mcp"
        assert cfg.command is None


# ── Tests for MCPBridge (mocked) ──────────────────────────────────────────────


class FakeMCPSession:
    """A fake session for testing MCPBridge internals."""
    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._connected = False
        self._tools: list[Any] = []
        self._error: str | None = None

    @property
    def config(self) -> MCPServerConfig:
        return self._config

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def tools(self) -> list[Any]:
        return list(self._tools)

    @property
    def error(self) -> str | None:
        return self._error

    async def connect(self) -> list[Any]:
        self._connected = True
        return self._tools

    async def disconnect(self) -> None:
        self._connected = False
        self._tools = []

    async def call_tool(self, name: str, arguments: dict[str, object]) -> str:
        return f"called {name} with {arguments}"


class TestMCPBridge:
    def test_no_servers_returns_empty(self) -> None:
        """No servers configured = no tools."""
        bridge = MCPBridge([])
        tools = bridge.start()
        assert tools == []
        bridge.disconnect_all()
        assert not bridge.is_any_connected

    def test_invalid_config_returns_empty(self) -> None:
        """Invalid server configs are skipped."""
        bridge = MCPBridge([{"name": "", "transport": "stdio"}])
        tools = bridge.start()
        assert tools == []

    def test_get_server_info_empty(self) -> None:
        """No servers = empty info list."""
        bridge = MCPBridge([])
        assert bridge.get_server_info() == []

    def test_total_tool_count_zero(self) -> None:
        """No servers = zero tools."""
        bridge = MCPBridge([])
        assert bridge.total_tool_count == 0

    def test_is_any_connected_false(self) -> None:
        """No servers = not connected."""
        bridge = MCPBridge([])
        assert not bridge.is_any_connected

    def test_wrap_tool_creates_valid_native_tool(self) -> None:
        """Verify _wrap_tool creates a correctly formed Tool object."""
        from mcp import types as mcp_types

        bridge = MCPBridge([])

        # Create a minimal mock MCP tool
        mock_tool = MagicMock(spec=mcp_types.Tool)
        mock_tool.name = "query"
        mock_tool.description = "Execute a SQL query"
        mock_tool.inputSchema = {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL query"}
            },
            "required": ["sql"],
        }

        native = bridge._wrap_tool(mock_tool, "sqlite")
        assert native.name == "sqlite/query"
        assert "SQL" in native.description
        assert native.input_schema["type"] == "object"
        props: dict[str, object] = native.input_schema.get("properties", {})  # type: ignore[assignment]
        assert "sql" in props
        assert not native.read_only

        # Test that the execute function returns a string
        result = native.execute({"sql": "SELECT 1"}, ToolContext(working_directory="."))
        assert isinstance(result, str)


# ── Security tests ─────────────────────────────────────────────────────────────


class TestMCPBridgeSecurity:
    """Verify SSRF protection and host allowlisting for MCP SSE servers."""

    def test_parse_rejects_private_ip_sse(self) -> None:
        """SSE URLs pointing to private IPs should be rejected by SSRF protection."""
        configs = parse_server_configs([
            {
                "name": "bad-server",
                "transport": "sse",
                "url": "http://192.168.1.1:8080/mcp",
            }
        ])
        assert len(configs) == 0  # Should be filtered out by SSRF check

    def test_parse_rejects_loopback_sse(self) -> None:
        """SSE URLs pointing to loopback should be rejected."""
        configs = parse_server_configs([
            {
                "name": "local-server",
                "transport": "sse",
                "url": "http://127.0.0.1:8080/mcp",
            }
        ])
        assert len(configs) == 0

    def test_parse_accepts_public_sse(self) -> None:
        """SSE URLs pointing to public hosts should be accepted."""
        configs = parse_server_configs([
            {
                "name": "public-server",
                "transport": "sse",
                "url": "https://api.example.com/mcp",
            }
        ])
        assert len(configs) == 1
        assert configs[0].name == "public-server"

    def test_parse_accepts_https_public_url(self) -> None:
        """HTTPS SSE URLs to public hosts should be accepted."""
        configs = parse_server_configs([
            {
                "name": "github-api",
                "transport": "sse",
                "url": "https://api.github.com/mcp",
            }
        ])
        assert len(configs) == 1
        assert configs[0].name == "github-api"

    def test_parse_stdio_not_affected_by_ssrf(self) -> None:
        """Stdio transport should not be blocked (it doesn't make network requests)."""
        configs = parse_server_configs([
            {
                "name": "local-tool",
                "transport": "stdio",
                "command": "uvx",
                "args": ["mcp-server-sqlite"],
            }
        ])
        assert len(configs) == 1
        assert configs[0].name == "local-tool"

    def test_parse_knows_verify_tls_default(self) -> None:
        """verify_tls should default to True for SSE configs."""
        configs = parse_server_configs([
            {
                "name": "test",
                "transport": "sse",
                "url": "https://api.example.com/mcp",
            }
        ])
        assert len(configs) == 1
        assert configs[0].verify_tls is True

    def test_parse_reads_allowed_hosts(self) -> None:
        """allowed_hosts from config should be parsed."""
        configs = parse_server_configs([
            {
                "name": "test",
                "transport": "sse",
                "url": "https://api.example.com/mcp",
                "allowed_hosts": ["api.example.com"],
            }
        ])
        assert len(configs) == 1
        assert configs[0].allowed_hosts == ["api.example.com"]

    def test_bridge_applys_global_allowed_hosts(self) -> None:
        """Global allowed_hosts should apply to SSE servers without their own list."""
        bridge = MCPBridge(
            [{"name": "test", "transport": "sse", "url": "https://api.example.com/mcp"}],
            allowed_hosts=["api.example.com"],
        )
        # Access internal sessions to check config
        for session in bridge._sessions.values():
            assert session.config.allowed_hosts == ["api.example.com"]
        bridge.disconnect_all()

    def test_bridge_does_not_override_per_server_allowed_hosts(self) -> None:
        """Per-server allowed_hosts should take priority over global list."""
        bridge = MCPBridge(
            [{
                "name": "test",
                "transport": "sse",
                "url": "https://api.example.com/mcp",
                "allowed_hosts": ["specific.example.com"],
            }],
            allowed_hosts=["global.example.com"],
        )
        for session in bridge._sessions.values():
            assert session.config.allowed_hosts == ["specific.example.com"]
        bridge.disconnect_all()

    def test_check_allowed_host_allows_matching(self) -> None:
        """A host matching the allowlist should pass."""
        bridge = MCPBridge([])
        cfg = MCPServerConfig(
            name="test", transport="sse", url="https://api.example.com/mcp",
            allowed_hosts=["api.example.com"],
        )
        result = bridge._check_allowed_host(cfg)
        assert result is None

    def test_check_allowed_host_blocks_non_matching(self) -> None:
        """A host not in the allowlist should be blocked."""
        bridge = MCPBridge([])
        cfg = MCPServerConfig(
            name="test", transport="sse", url="https://evil.com/mcp",
            allowed_hosts=["api.example.com"],
        )
        result = bridge._check_allowed_host(cfg)
        assert result is not None
        assert "evil.com" in result
        assert "api.example.com" in result

    def test_check_allowed_host_no_restrictions(self) -> None:
        """With no allowed_hosts set, any host should pass."""
        bridge = MCPBridge([])
        cfg = MCPServerConfig(
            name="test", transport="sse", url="https://any-host.com/mcp",
        )
        assert bridge._check_allowed_host(cfg) is None

    def test_check_allowed_host_stdio_ignored(self) -> None:
        """Stdio transport should not be subject to host checks."""
        bridge = MCPBridge([])
        cfg = MCPServerConfig(
            name="test", transport="stdio", command="echo",
        )
        assert bridge._check_allowed_host(cfg) is None
