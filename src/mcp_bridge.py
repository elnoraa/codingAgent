"""MCP (Model Context Protocol) Bridge.

Connects to MCP servers, discovers their tools, and wraps them as native
``Tool`` objects that the Coding Agent can call seamlessly alongside
built-in tools.

Usage
-----
    bridge = MCPBridge([
        {
            "name": "sqlite",
            "transport": "stdio",
            "command": "uvx",
            "args": ["mcp-server-sqlite", "--db-path", "./data.db"],
        },
    ])
    tools = bridge.start()          # returns list[Tool]
    ...
    bridge.disconnect_all()
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from src.tools import Tool, ToolContext

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MCP_TOOL_CALL_TIMEOUT: float = 60.0
"""Maximum seconds to wait for a single MCP tool call to complete."""

MCP_CONNECT_TIMEOUT: float = 15.0
"""Maximum seconds to wait for an MCP server connection to be established."""


# ── Data types ────────────────────────────────────────────────────────────────


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    """Unique identifier for this server (e.g. ``"sqlite"``)."""

    transport: str
    """Transport type: ``"stdio"`` or ``"sse"``."""

    # Stdio fields
    command: str | None = None
    """Command to run for stdio transport (e.g. ``"uvx"``)."""
    args: list[str] | None = None
    """Arguments for the stdio command."""
    env: dict[str, str] | None = None
    """Optional environment variables for the stdio subprocess."""

    # SSE fields
    url: str | None = None
    """SSE endpoint URL (e.g. ``"https://api.example.com/mcp"``)."""
    headers: dict[str, str] | None = None
    """Optional HTTP headers for SSE transport."""
    verify_tls: bool = True
    """Whether to verify TLS certificates for SSE connections (default: True)."""
    allowed_hosts: list[str] | None = None
    """Optional: restrict SSE connections to specific hostnames only."""


# ── Helpers ───────────────────────────────────────────────────────────────────


def parse_server_configs(raw: list[dict[str, object]]) -> list[MCPServerConfig]:
    """Parse a list of raw MCP server config dicts into ``MCPServerConfig`` objects.

    Invalid entries (missing required fields) are logged and skipped.
    """
    configs: list[MCPServerConfig] = []
    for entry in raw:
        try:
            name = str(entry.get("name", ""))
            if not name:
                logger.warning("Skipping MCP server with empty name")
                continue
            transport = str(entry.get("transport", "stdio")).lower()
            if transport not in ("stdio", "sse"):
                logger.warning("Skipping MCP server %r: unknown transport %r", name, transport)
                continue

            cfg = MCPServerConfig(name=name, transport=transport)

            if transport == "stdio":
                command = entry.get("command")
                if not command:
                    logger.warning("Skipping MCP server %r: missing 'command' for stdio transport", name)
                    continue
                cfg.command = str(command)
                raw_args = entry.get("args")
                if isinstance(raw_args, list):
                    cfg.args = [str(a) for a in raw_args]
                raw_env = entry.get("env")
                if isinstance(raw_env, dict):
                    cfg.env = {str(k): str(v) for k, v in raw_env.items()}
            else:  # sse
                url = entry.get("url")
                if not url:
                    logger.warning("Skipping MCP server %r: missing 'url' for SSE transport", name)
                    continue
                cfg.url = str(url)
                raw_headers = entry.get("headers")
                if isinstance(raw_headers, dict):
                    cfg.headers = {str(k): str(v) for k, v in raw_headers.items()}
                # SSRF protection: block SSE URLs pointing to private/internal IPs
                try:
                    from src.utils import validate_url_target

                    ssrf_error = validate_url_target(str(url))
                    if ssrf_error:
                        logger.warning("Skipping MCP server %r: %s", name, ssrf_error)
                        continue
                except ImportError:
                    pass
                # Read optional security config
                cfg.verify_tls = bool(entry.get("verify_tls", True))
                raw_allowed = entry.get("allowed_hosts")
                if isinstance(raw_allowed, list):
                    cfg.allowed_hosts = [str(h) for h in raw_allowed]

            configs.append(cfg)
            logger.debug("Parsed MCP server config: name=%s transport=%s", name, transport)
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("Skipping invalid MCP server entry: %s", exc)
            continue
    return configs


def _serialize_tool_result(result: types.CallToolResult) -> str:
    """Convert an MCP ``CallToolResult`` into a plain string.

    Handles ``TextContent``, ``ImageContent``, ``EmbeddedResource``,
    and structured ``content`` blocks.
    """
    parts: list[str] = []
    for block in result.content:
        if isinstance(block, types.TextContent):
            parts.append(block.text)
        elif isinstance(block, types.ImageContent):
            parts.append(f"[Image: {block.mimeType or 'unknown'} ({len(block.data)} bytes)]")
        elif isinstance(block, types.EmbeddedResource):
            parts.append(f"[Embedded resource: {block.resource.uri}]")
        elif hasattr(block, "type"):
            # Duck-typing for test fakes and compatible objects
            t = block.type  # type: ignore[union-attr]
            if t == "text" and hasattr(block, "text"):
                parts.append(str(block.text))  # type: ignore[union-attr]
            elif t == "image":
                mime = getattr(block, "mimeType", None) or "unknown"
                data_len = len(getattr(block, "data", "") or "")
                parts.append(f"[Image: {mime} ({data_len} bytes)]")
            elif t == "resource" and hasattr(block, "resource"):
                uri = getattr(block.resource, "uri", str(block.resource))  # type: ignore[union-attr]
                parts.append(f"[Embedded resource: {uri}]")
            else:
                parts.append(str(block))
        else:
            parts.append(str(block))
    text = "\n".join(parts)

    if result.isError:
        text = f"Error: {text}"

    return text


# ── MCPSession ────────────────────────────────────────────────────────────────


class MCPSession:
    """Manages a single connection to an MCP server.

    Wraps the lifecycle of ``stdio_client`` / ``sse_client`` and
    ``ClientSession`` from the MCP Python SDK.
    """

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._session: ClientSession | None = None
        self._read: Any = None
        self._write: Any = None
        self._ctx_stack: Any = None  # context manager for transport
        self._tools: list[types.Tool] = []
        self._error: str | None = None

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def config(self) -> MCPServerConfig:
        return self._config

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def tools(self) -> list[types.Tool]:
        return list(self._tools)

    @property
    def error(self) -> str | None:
        return self._error

    # ── Connection lifecycle ──────────────────────────────────────────────

    async def connect(self) -> list[types.Tool]:
        """Connect to the MCP server, initialize the session, and discover tools.

        Returns the list of available tools.
        Raises on failure.
        """
        cfg = self._config

        if cfg.transport == "stdio":
            if not cfg.command:
                raise ValueError(f"Server {cfg.name!r}: missing command for stdio transport")
            server_params = StdioServerParameters(
                command=cfg.command,
                args=cfg.args or [],
                env=cfg.env,
            )
            self._ctx_stack = stdio_client(server_params)
        else:
            if not cfg.url:
                raise ValueError(f"Server {cfg.name!r}: missing url for SSE transport")
            self._ctx_stack = sse_client(
                url=cfg.url,
                headers=cfg.headers,
                timeout=MCP_CONNECT_TIMEOUT,
            )

        transport = await self._ctx_stack.__aenter__()
        self._read, self._write = transport

        self._session = await ClientSession(self._read, self._write).__aenter__()
        await self._session.initialize()

        # Discover tools
        tools_result = await self._session.list_tools()
        self._tools = list(tools_result.tools)

        logger.info(
            "MCP server %r connected (transport=%s, tools=%d)",
            cfg.name,
            cfg.transport,
            len(self._tools),
        )
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, object]) -> str:
        """Call a tool on the MCP server and return the serialized result.

        Raises on connection/execution errors.
        """
        if self._session is None:
            raise ConnectionError(f"MCP server {self._config.name!r} is not connected")

        result = await self._session.call_tool(name, arguments)
        return _serialize_tool_result(result)

    async def disconnect(self) -> None:
        """Disconnect from the MCP server and clean up resources."""
        error = None
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception as exc:
                error = exc
                logger.warning("Error closing session for %r: %s", self._config.name, exc)
            self._session = None

        if self._ctx_stack is not None:
            try:
                await self._ctx_stack.__aexit__(None, None, None)
            except Exception as exc:
                if error is None:
                    error = exc
                logger.warning("Error closing transport for %r: %s", self._config.name, exc)
            self._ctx_stack = None
            self._read = None
            self._write = None

        self._tools = []
        logger.info("MCP server %r disconnected", self._config.name)


# ── MCPBridge ─────────────────────────────────────────────────────────────────


class MCPBridge:
    """Bridge that connects to multiple MCP servers and wraps their tools.

    Runs an asyncio event loop in a background daemon thread, keeping
    MCP sessions alive for the duration of the agent session.
    """

    def __init__(
        self,
        servers_config: list[dict[str, object]],
        allowed_hosts: list[str] | None = None,
    ) -> None:
        self._server_configs = parse_server_configs(servers_config)
        self._sessions: dict[str, MCPSession] = {}
        self._native_tools: list[Tool] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._started = False
        self._allowed_hosts = allowed_hosts or []

        # Apply global allowed_hosts to any SSE server that doesn't have its own list
        if self._allowed_hosts:
            for cfg in self._server_configs:
                if cfg.transport == "sse" and not cfg.allowed_hosts:
                    cfg.allowed_hosts = list(self._allowed_hosts)

    # ── Public API ────────────────────────────────────────────────────────

    def start(self) -> list[Tool]:
        """Start the background event loop, connect to all configured servers,
        discover their tools, and return them as native ``Tool`` objects.

        May return an empty list if no servers are configured or all
        connections fail.
        """
        if self._started:
            return list(self._native_tools)
        self._started = True

        if not self._server_configs:
            logger.info("No MCP servers configured")
            return []

        # Create session objects
        for cfg in self._server_configs:
            self._sessions[cfg.name] = MCPSession(cfg)

        # Start the background event loop thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=_run_event_loop,
            args=(self._loop,),
            daemon=True,
            name="mcp-bridge",
        )
        self._thread.start()

        # Connect to all servers and discover tools
        future = asyncio.run_coroutine_threadsafe(
            self._connect_all_async(),
            self._loop,
        )
        try:
            future.result(timeout=max(MCP_CONNECT_TIMEOUT + 5, 30))
        except Exception as exc:
            logger.error("MCP bridge initialization error: %s", exc)

        # Build native tool objects from discovered MCP tools
        native_tools: list[Tool] = []
        for session in self._sessions.values():
            for mcp_tool in session.tools:
                native_tools.append(self._wrap_tool(mcp_tool, session.config.name))

        self._native_tools = native_tools
        logger.info(
            "MCP bridge started: %d tool(s) from %d server(s)",
            len(native_tools),
            len(self._sessions),
        )
        return native_tools

    def disconnect_all(self) -> None:
        """Disconnect all MCP sessions and stop the background event loop."""
        if not self._loop:
            return

        future = asyncio.run_coroutine_threadsafe(
            self._disconnect_all_async(),
            self._loop,
        )
        try:
            future.result(timeout=10)
        except Exception as exc:
            logger.warning("Error during MCP disconnect: %s", exc)

        self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        self._loop = None
        self._thread = None
        self._sessions.clear()
        self._native_tools.clear()
        self._started = False
        logger.info("MCP bridge stopped")

    def get_server_info(self) -> list[dict[str, Any]]:
        """Return status information for all configured servers.

        Each entry contains:
        - ``name``: server name
        - ``transport``: transport type
        - ``connected``: whether the session is active
        - ``tool_count``: number of tools discovered
        - ``tools``: list of dicts with ``name`` and ``description``
        - ``error``: error message if disconnected/failed
        """
        infos: list[dict[str, Any]] = []
        for session in self._sessions.values():
            info: dict[str, Any] = {
                "name": session.config.name,
                "transport": session.config.transport,
                "connected": session.is_connected,
                "tool_count": session.tool_count,
                "tools": [
                    {
                        "name": f"{session.config.name}/{t.name}",
                        "description": t.description or "",
                    }
                    for t in session.tools
                ],
            }
            if session.error:
                info["error"] = session.error
            infos.append(info)
        return infos

    @property
    def total_tool_count(self) -> int:
        """Total number of MCP tools across all connected servers."""
        return sum(s.tool_count for s in self._sessions.values())

    @property
    def is_any_connected(self) -> bool:
        """Whether at least one MCP server is connected."""
        return any(s.is_connected for s in self._sessions.values())

    # ── Internal: tool wrapping ───────────────────────────────────────────

    def _wrap_tool(self, mcp_tool: types.Tool, server_name: str) -> Tool:
        """Wrap an MCP ``types.Tool`` as the agent's native ``Tool`` object."""
        full_name = f"{server_name}/{mcp_tool.name}"
        input_schema: dict[str, object] = {}
        if mcp_tool.inputSchema is not None:
            raw: object = mcp_tool.inputSchema
            # Handle both pydantic BaseModel and plain dict
            if hasattr(raw, "model_dump"):
                input_schema = dict(raw.model_dump())  # type: ignore[union-attr]
            elif isinstance(raw, dict):
                input_schema = dict(raw)
            else:
                input_schema = {"type": "object", "properties": {}}

        server = server_name
        tool_name = mcp_tool.name

        def _execute(args: dict[str, object], ctx: ToolContext) -> str:
            return self._execute_mcp(server, tool_name, args)

        return Tool(
            name=full_name,
            description=mcp_tool.description or f"MCP tool: {full_name}",
            input_schema=input_schema,
            execute=_execute,
        )

    def _execute_mcp(self, server_name: str, tool_name: str, args: dict[str, object]) -> str:
        """Execute an MCP tool call. Runs the coroutine on the background loop."""
        if self._loop is None:
            return f"Error: MCP bridge is not running (server {server_name!r})"

        session = self._sessions.get(server_name)
        if session is None:
            return f"Error: Unknown MCP server {server_name!r}"

        if not session.is_connected:
            return f"Error: MCP server {server_name!r} is not connected"

        future = asyncio.run_coroutine_threadsafe(
            session.call_tool(tool_name, args),
            self._loop,
        )
        try:
            return future.result(timeout=MCP_TOOL_CALL_TIMEOUT)
        except TimeoutError:
            return f"Error: MCP tool {server_name}/{tool_name} timed out after {MCP_TOOL_CALL_TIMEOUT}s"
        except Exception as exc:
            return f"Error calling MCP tool {server_name}/{tool_name}: {exc}"

    # ── Internal: async connect/disconnect ────────────────────────────────

    async def _connect_all_async(self) -> None:
        """Connect to all configured MCP servers concurrently.

        Failed connections are logged but do not block other servers.
        """
        tasks: list[asyncio.Task[None]] = []
        for session in self._sessions.values():
            tasks.append(asyncio.create_task(self._connect_one(session)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _connect_one(self, session: MCPSession) -> None:
        """Connect a single session, catching and logging errors."""
        # Check host allowlist for SSE connections
        host_error = self._check_allowed_host(session.config)
        if host_error:
            session._error = host_error  # type: ignore[attr-defined]
            logger.warning("MCP server %r blocked: %s", session.config.name, host_error)
            return
        try:
            await session.connect()
        except Exception as exc:
            logger.warning(
                "Failed to connect to MCP server %r: %s",
                session.config.name,
                exc,
            )
            # Mark error on session
            session._error = str(exc)  # type: ignore[attr-defined]

    def _check_allowed_host(self, config: MCPServerConfig) -> str | None:
        """Check if an SSE server host is in the allowed hosts list.

        Returns an error message if blocked, None if allowed.
        """
        if config.transport != "sse" or not config.url:
            return None
        if not config.allowed_hosts:
            return None  # No restrictions configured — allow

        from urllib.parse import urlparse

        try:
            hostname = urlparse(config.url).hostname
        except Exception:
            return None

        if hostname and hostname not in config.allowed_hosts:
            return (
                f"Error: MCP server '{config.name}' host '{hostname}' is not in the "
                f"allowed hosts list: {config.allowed_hosts}"
            )
        return None

    async def _disconnect_all_async(self) -> None:
        """Disconnect all sessions concurrently."""
        tasks = [asyncio.create_task(s.disconnect()) for s in self._sessions.values() if s.is_connected]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


# ── Background event loop runner ──────────────────────────────────────────────


def _run_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Run an asyncio event loop forever (daemon thread target)."""
    asyncio.set_event_loop(loop)
    loop.run_forever()
