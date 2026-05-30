"""Tests for the list_agents tool."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.tools import ToolContext
from src.tools.list_agents import _execute_list_agents, list_agents_tool


def _make_context(orchestrator: object | None = None) -> ToolContext:
    ctx = ToolContext(working_directory="/tmp")
    ctx.orchestrator = orchestrator
    ctx.agent_id = "main"
    return ctx


def _make_handle(
    agent_id: str = "sub-test",
    role: str = "worker",
    status: str = "idle",
    message_count: int = 1,
    result: object = None,
) -> MagicMock:
    h = MagicMock()
    h.agent_id = agent_id
    h.role = role
    h.status = status
    h.message_count = message_count
    h.result = result
    return h


class TestListAgentsTool:
    """Verify list_agents tool metadata and execution."""

    def test_tool_definition(self) -> None:
        assert list_agents_tool.name == "list_agents"
        assert list_agents_tool.read_only is True

    def test_execute_no_orchestrator(self) -> None:
        ctx = _make_context(orchestrator=None)
        result = _execute_list_agents({}, ctx)
        assert "No orchestrator" in result

    def test_execute_no_agents(self) -> None:
        orch = MagicMock()
        orch.list_agents.return_value = []
        ctx = _make_context(orchestrator=orch)
        result = _execute_list_agents({}, ctx)
        assert "No sub-agents found" in result

    def test_execute_with_agents(self) -> None:
        orch = MagicMock()
        handle = _make_handle(agent_id="sub-1", role="worker", status="idle")
        orch.list_agents.return_value = [handle]
        ctx = _make_context(orchestrator=orch)
        result = _execute_list_agents({}, ctx)
        assert "sub-1" in result
        assert "worker" in result
        assert "idle" in result

    def test_execute_with_multiple_agents(self) -> None:
        orch = MagicMock()
        h1 = _make_handle(agent_id="worker-1", role="worker", status="completed")
        h2 = _make_handle(agent_id="planner-2", role="plan", status="running")
        orch.list_agents.return_value = [h1, h2]
        ctx = _make_context(orchestrator=orch)
        result = _execute_list_agents({}, ctx)
        assert "worker-1" in result
        assert "planner-2" in result
        assert "2 total" in result

    def test_execute_shows_result_preview(self) -> None:
        orch = MagicMock()
        result_obj = MagicMock()
        result_obj.summary = "All tests passed!"
        result_obj.output = ""
        result_obj.error = None
        handle = _make_handle(
            agent_id="sub-done",
            status="completed",
            result=result_obj,
        )
        orch.list_agents.return_value = [handle]
        ctx = _make_context(orchestrator=orch)
        result = _execute_list_agents({}, ctx)
        assert "All tests passed!" in result

    def test_execute_shows_error_preview(self) -> None:
        orch = MagicMock()
        result_obj = MagicMock()
        result_obj.summary = ""
        result_obj.output = ""
        result_obj.error = "Connection failed"
        handle = _make_handle(
            agent_id="sub-fail",
            status="error",
            result=result_obj,
        )
        orch.list_agents.return_value = [handle]
        ctx = _make_context(orchestrator=orch)
        result = _execute_list_agents({}, ctx)
        assert "Connection failed" in result
        assert "Error" in result

    def test_status_icons(self) -> None:
        orch = MagicMock()
        h_idle = _make_handle(agent_id="a", status="idle")
        h_run = _make_handle(agent_id="b", status="running")
        h_done = _make_handle(agent_id="c", status="completed")
        h_err = _make_handle(agent_id="d", status="error")
        orch.list_agents.return_value = [h_idle, h_run, h_done, h_err]
        ctx = _make_context(orchestrator=orch)
        result = _execute_list_agents({}, ctx)
        # Icons: idle=○, running=⟳, completed=✓, error=✗
        assert "○" in result  # idle
        assert "✓" in result  # completed
        assert "✗" in result  # error
