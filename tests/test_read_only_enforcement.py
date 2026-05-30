"""Tests for read-only enforcement in tools."""

from __future__ import annotations

from src.tools import Tool, ToolContext, ToolRegistry


def _execute_with_read_only_check(
    tool: Tool,
    args: dict[str, object],
    ctx: ToolContext,
    read_only: bool,
) -> str:
    """Replicate the enforcement logic from client.py chat_with_tools()."""
    if read_only and not tool.read_only:
        return (
            f'Error: tool "{tool.name}" is not available in read-only mode. '
            f"Switch to CODE mode (use /code) to use this tool."
        )
    return tool.execute(args, ctx)


def test_read_only_mode_blocks_write_tools() -> None:
    """When read_only=True, calling a write tool should return an error."""
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="test_write",
            description="A write tool",
            input_schema={"type": "object", "properties": {}},
            execute=lambda a, c: "executed!",
            read_only=False,
        )
    )
    registry.register(
        Tool(
            name="test_read",
            description="A read tool",
            input_schema={"type": "object", "properties": {}},
            execute=lambda a, c: "data",
            read_only=True,
        )
    )

    ctx = ToolContext(working_directory="/tmp")

    # Write tool should be blocked
    tool = registry.get("test_write")
    assert tool is not None
    result = _execute_with_read_only_check(tool, {}, ctx, read_only=True)
    assert "not available in read-only mode" in result
    assert "executed!" not in result

    # Read-only tool should still work
    tool2 = registry.get("test_read")
    assert tool2 is not None
    result2 = _execute_with_read_only_check(tool2, {}, ctx, read_only=True)
    assert result2 == "data"


def test_code_mode_allows_write_tools() -> None:
    """When read_only=False, write tools should execute normally."""
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="test_write",
            description="A write tool",
            input_schema={},
            execute=lambda a, c: "executed!",
            read_only=False,
        )
    )

    ctx = ToolContext(working_directory="/tmp")
    tool = registry.get("test_write")
    assert tool is not None
    result = _execute_with_read_only_check(tool, {"key": "value"}, ctx, read_only=False)
    assert result == "executed!"


def test_read_only_mode_allows_read_tools() -> None:
    """Read-only tools should work in both modes."""
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="test_read",
            description="A read tool",
            input_schema={},
            execute=lambda a, c: "data",
            read_only=True,
        )
    )

    ctx = ToolContext(working_directory="/tmp")
    tool = registry.get("test_read")
    assert tool is not None
    result = _execute_with_read_only_check(tool, {}, ctx, read_only=False)
    assert result == "data"
