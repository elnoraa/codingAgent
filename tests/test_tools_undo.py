"""Tests for the undo/rollback tool."""

from __future__ import annotations

from tools import ToolContext
from tools.undo_tool import undo_tool


def _make_context_with_snapshot() -> ToolContext:
    """Create a context with one file snapshot."""
    ctx = ToolContext(working_directory="/tmp")
    ctx.file_snapshots = {}
    # Manually add a snapshot (simulates what write_file does)
    ctx.file_snapshots["/tmp/test.py"] = [("1234567890.0", "original content")]
    return ctx


def test_tool_definition() -> None:
    """Tool metadata should be correct."""
    assert undo_tool.name == "undo"


def test_execute_list_no_snapshots() -> None:
    """List action with no snapshots should return appropriate message."""
    ctx = ToolContext(working_directory="/tmp")
    execute_fn = undo_tool.execute
    result = execute_fn({"action": "list"}, ctx)
    assert "No snapshots" in result


def test_execute_list_with_snapshots() -> None:
    """List action with snapshots should show them."""
    ctx = _make_context_with_snapshot()
    execute_fn = undo_tool.execute
    result = execute_fn({"action": "list"}, ctx)
    assert "test.py" in result
    assert "original content" in result


def test_execute_revert_invalid_path() -> None:
    """Revert with a path that has no snapshots should return error."""
    ctx = _make_context_with_snapshot()
    execute_fn = undo_tool.execute
    result = execute_fn({"action": "revert", "path": "/tmp/nonexistent.py"}, ctx)
    assert "No snapshots" in result or "not found" in result


def test_execute_invalid_action() -> None:
    """Invalid action should return error."""
    ctx = ToolContext(working_directory="/tmp")
    execute_fn = undo_tool.execute
    result = execute_fn({"action": "unknown"}, ctx)
    assert 'action must be "list" or "revert"' in result


def test_execute_revert_missing_path() -> None:
    """Revert without a path should return error."""
    ctx = _make_context_with_snapshot()
    execute_fn = undo_tool.execute
    result = execute_fn({"action": "revert"}, ctx)
    assert "path is required" in result
