"""Tests for the terminate_agent tool."""

from __future__ import annotations

from unittest.mock import MagicMock

from tools import ToolContext
from tools.terminate_agent import terminate_agent_tool, _execute_terminate_agent


def _make_context(orchestrator: object | None = None) -> ToolContext:
    ctx = ToolContext(working_directory="/tmp")
    ctx.orchestrator = orchestrator
    ctx.agent_id = "main"
    return ctx


class TestTerminateAgentTool:
    """Verify terminate_agent tool metadata and execution."""

    def test_tool_definition(self) -> None:
        assert terminate_agent_tool.name == "terminate_agent"
        assert terminate_agent_tool.read_only is False

    def test_execute_no_orchestrator(self) -> None:
        ctx = _make_context(orchestrator=None)
        result = _execute_terminate_agent({"agent_id": "sub-test"}, ctx)
        assert "No orchestrator" in result

    def test_execute_missing_agent_id(self) -> None:
        orch = MagicMock()
        ctx = _make_context(orchestrator=orch)
        result = _execute_terminate_agent({}, ctx)
        assert "agent_id" in result.lower() or "required" in result.lower()
        orch.terminate_agent.assert_not_called()

    def test_execute_empty_agent_id(self) -> None:
        orch = MagicMock()
        ctx = _make_context(orchestrator=orch)
        result = _execute_terminate_agent({"agent_id": ""}, ctx)
        assert "agent_id" in result.lower() or "required" in result.lower()

    def test_execute_success(self) -> None:
        orch = MagicMock()
        orch.terminate_agent.return_value = True
        ctx = _make_context(orchestrator=orch)
        result = _execute_terminate_agent({"agent_id": "sub-test"}, ctx)
        assert "terminated" in result.lower()
        assert "sub-test" in result
        orch.terminate_agent.assert_called_once_with("sub-test")

    def test_execute_agent_not_found(self) -> None:
        orch = MagicMock()
        orch.terminate_agent.return_value = False
        ctx = _make_context(orchestrator=orch)
        result = _execute_terminate_agent({"agent_id": "nonexistent"}, ctx)
        assert "not found" in result.lower()

    def test_execute_orchestrator_exception(self) -> None:
        orch = MagicMock()
        orch.terminate_agent.side_effect = RuntimeError("Something broke")
        ctx = _make_context(orchestrator=orch)
        result = _execute_terminate_agent({"agent_id": "sub-test"}, ctx)
        assert "Error" in result
        assert "Something broke" in result
