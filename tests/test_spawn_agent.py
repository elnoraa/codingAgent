"""Tests for the spawn_agent tool."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.tools import ToolContext
from src.tools.spawn_agent import spawn_agent_tool, _execute_spawn_agent


def _make_context(orchestrator: object | None = None) -> ToolContext:
    ctx = ToolContext(working_directory="/tmp")
    ctx.orchestrator = orchestrator
    ctx.agent_id = "main"
    return ctx


def _make_orchestrator() -> MagicMock:
    """Create a mock orchestrator for testing."""
    orch = MagicMock()
    handle = MagicMock()
    handle.agent_id = "sub-abc123"
    orch.spawn_agent.return_value = handle
    return orch


class TestSpawnAgentTool:
    """Verify spawn_agent tool metadata and execution."""

    def test_tool_definition(self) -> None:
        assert spawn_agent_tool.name == "spawn_agent"
        assert spawn_agent_tool.read_only is False

    def test_execute_no_orchestrator(self) -> None:
        ctx = _make_context(orchestrator=None)
        result = _execute_spawn_agent({"task": "do something"}, ctx)
        assert "No orchestrator" in result

    def test_execute_missing_task(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_spawn_agent({}, ctx)
        assert "task" in result.lower()
        assert "required" in result.lower()
        orch.spawn_agent.assert_not_called()

    def test_execute_empty_task(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_spawn_agent({"task": ""}, ctx)
        assert "task" in result.lower()

    def test_execute_success(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_spawn_agent({"task": "write tests"}, ctx)
        assert "sub-abc123" in result
        assert "Spawed" in result
        orch.spawn_agent.assert_called_once()

    def test_execute_invalid_role(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_spawn_agent({"task": "test", "role": "superadmin"}, ctx)
        assert "Unknown role" in result
        orch.spawn_agent.assert_not_called()

    def test_execute_with_model_override(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        _execute_spawn_agent({"task": "test", "model": "claude-3-opus"}, ctx)
        orch.spawn_agent.assert_called_once()
        _, kwargs = orch.spawn_agent.call_args
        assert kwargs.get("model") == "claude-3-opus"

    def test_execute_passes_parent_id(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        ctx.agent_id = "parent-1"
        _execute_spawn_agent({"task": "test"}, ctx)
        orch.spawn_agent.assert_called_once()
        _, kwargs = orch.spawn_agent.call_args
        assert kwargs.get("parent_id") == "parent-1"

    def test_role_code_valid(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_spawn_agent({"task": "test", "role": "code"}, ctx)
        assert "Error" not in result

    def test_role_plan_valid(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_spawn_agent({"task": "test", "role": "plan"}, ctx)
        assert "Error" not in result

    def test_role_worker_valid(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_spawn_agent({"task": "test", "role": "worker"}, ctx)
        assert "Error" not in result

    def test_role_observer_valid(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_spawn_agent({"task": "test", "role": "observer"}, ctx)
        assert "Error" not in result

    def test_execute_orchestrator_runtime_error(self) -> None:
        orch = _make_orchestrator()
        orch.spawn_agent.side_effect = RuntimeError("Too deep")
        ctx = _make_context(orchestrator=orch)
        result = _execute_spawn_agent({"task": "test"}, ctx)
        assert "Error" in result
        assert "Too deep" in result
