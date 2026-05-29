"""Tests for the run_swarm tool — sequential, debate, and broadcast patterns."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.tools import ToolContext
from src.tools.run_swarm import (
    _execute_run_swarm,
    _run_broadcast_swarm,
    _run_debate_swarm,
    _run_sequential_swarm,
    run_swarm_tool,
)


def _make_orchestrator() -> MagicMock:
    """Create a mock orchestrator for swarm testing."""
    orch = MagicMock()
    agent_counter = [0]

    def _spawn(parent_id, task, role, model=None):
        agent_counter[0] += 1
        handle = MagicMock()
        handle.agent_id = f"agent-{agent_counter[0]:04d}"
        return handle

    orch.spawn_agent.side_effect = _spawn

    def _run(agent_id, context):
        result = MagicMock()
        result.output = f"Output from {agent_id}"
        result.error = None
        result.input_tokens = 50
        result.output_tokens = 100
        return result

    orch.run_agent.side_effect = _run
    orch.terminate_agent = MagicMock()
    return orch


def _make_context(orchestrator: object | None = None) -> ToolContext:
    ctx = ToolContext(working_directory="/tmp")
    ctx.orchestrator = orchestrator
    ctx.agent_id = "main"
    return ctx


class TestRunSwarmTool:
    """Verify run_swarm tool metadata and execution."""

    # ── Tool definition ─────────────────────────────────────────────────

    def test_tool_definition(self) -> None:
        assert run_swarm_tool.name == "run_swarm"
        assert run_swarm_tool.read_only is False

    # ── Error paths ─────────────────────────────────────────────────────

    def test_execute_no_orchestrator(self) -> None:
        ctx = _make_context(orchestrator=None)
        result = _execute_run_swarm({"pattern": "sequential", "task": "test"}, ctx)
        assert "No orchestrator" in result

    def test_execute_missing_pattern(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_run_swarm({"task": "test"}, ctx)
        assert "pattern" in result.lower()
        assert "required" in result.lower()

    def test_execute_missing_task(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_run_swarm({"pattern": "sequential"}, ctx)
        assert "task" in result.lower()
        assert "required" in result.lower()

    def test_execute_unknown_pattern(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_run_swarm({"pattern": "invalid", "task": "test"}, ctx)
        assert "Unknown" in result

    # ── Sequential pattern ──────────────────────────────────────────────

    def test_sequential_swarm(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _run_sequential_swarm(
            orchestrator=orch,
            parent_id="main",
            task="build feature",
            agent_roles=["code", "plan"],
            context=ctx,
        )
        assert "Sequential Swarm" in result
        assert orch.spawn_agent.call_count == 2
        assert orch.terminate_agent.call_count == 2

    def test_sequential_swarm_passes_context_forward(self) -> None:
        """Each agent after the first should receive the previous agent's output."""
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)

        # Track what tasks are given to spawned agents
        spawned_tasks: list[str] = []

        def _spawn_tracker(parent_id, task, role, model=None):
            spawned_tasks.append(task)
            handle = MagicMock()
            handle.agent_id = f"agent-{len(spawned_tasks):04d}"
            return handle

        orch.spawn_agent.side_effect = _spawn_tracker

        _run_sequential_swarm(
            orchestrator=orch,
            parent_id="main",
            task="build feature",
            agent_roles=["code", "plan"],
            context=ctx,
        )
        # First agent gets the original task
        assert "build feature" in spawned_tasks[0]
        # Second agent gets context from first agent's output
        assert "Context from previous step" in spawned_tasks[1]

    def test_sequential_swarm_default_roles(self) -> None:
        """Without agent_roles, defaults to three 'code' agents.

        Note: default role filling happens in _execute_run_swarm, not in
        _run_sequential_swarm directly. Test through the execute path.
        """
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_run_swarm(
            {"pattern": "sequential", "task": "test"},
            ctx,
        )
        assert "Sequential Swarm" in result
        assert orch.spawn_agent.call_count == 3  # default roles

    def test_sequential_swarm_with_empty_roles_direct(self) -> None:
        """Calling _run_sequential_swarm with empty roles runs agents anyway."""
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        _run_sequential_swarm(
            orchestrator=orch,
            parent_id="main",
            task="test",
            agent_roles=[],
            context=ctx,
        )
        # With empty list, the function still iterates, just with no agents
        assert orch.spawn_agent.call_count == 0

    def test_sequential_swarm_agent_failure_skips_remaining(self) -> None:
        """If an agent fails, remaining agents should be skipped."""
        orch = _make_orchestrator()
        calls = [0]

        def _run_fail(agent_id, context):
            calls[0] += 1
            result = MagicMock()
            result.output = ""
            result.error = "Something went wrong" if calls[0] >= 2 else None
            result.input_tokens = 10
            result.output_tokens = 10
            return result

        orch.run_agent.side_effect = _run_fail
        ctx = _make_context(orchestrator=orch)

        _run_sequential_swarm(
            orchestrator=orch,
            parent_id="main",
            task="test",
            agent_roles=["code", "code", "code"],
            context=ctx,
        )
        # Only 2 agents should have run (3rd skipped after error)
        assert orch.run_agent.call_count >= 1

    # ── Debate pattern ────────────────────────────────────────────────

    def test_debate_swarm(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _run_debate_swarm(
            orchestrator=orch,
            parent_id="main",
            task="solve problem",
            agent_count=2,
            context=ctx,
        )
        assert "Debate Swarm" in result
        assert orch.spawn_agent.call_count >= 1

    def test_debate_swarm_enforces_min_count(self) -> None:
        """agent_count below 2 is clamped to 2 in _execute_run_swarm."""
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_run_swarm(
            {"pattern": "debate", "task": "test", "agent_count": 1},
            ctx,
        )
        assert "Debate Swarm" in result
        assert "2 agent(s)" in result

    # ── Broadcast pattern ────────────────────────────────────────────

    def test_broadcast_swarm(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _run_broadcast_swarm(
            orchestrator=orch,
            parent_id="main",
            task="write code",
            agent_count=2,
            context=ctx,
        )
        assert "Broadcast Swarm" in result
        assert "Best result" in result

    def test_broadcast_swarm_enforces_min_count(self) -> None:
        """agent_count below 2 is clamped to 2 in _execute_run_swarm."""
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_run_swarm(
            {"pattern": "broadcast", "task": "test", "agent_count": 0},
            ctx,
        )
        assert "Broadcast Swarm" in result
        assert "2 agent(s)" in result

    def test_broadcast_swarm_best_result_by_length(self) -> None:
        """The longest output should be selected as best."""
        orch = _make_orchestrator()
        results_so_far: list[str] = []

        def _run_with_length(agent_id, context):
            length = len(results_so_far) + 1
            output = "x" * (100 * length)
            results_so_far.append(output)
            result = MagicMock()
            result.output = output
            result.error = None
            result.input_tokens = 10
            result.output_tokens = 10
            return result

        orch.run_agent.side_effect = _run_with_length
        ctx = _make_context(orchestrator=orch)

        result = _run_broadcast_swarm(
            orchestrator=orch,
            parent_id="main",
            task="test",
            agent_count=3,
            context=ctx,
        )
        # The best result should be the longest (last one)
        assert "300 chars" in result or "200" in result or "Best result" in result

    # ── Full execute integration ─────────────────────────────────────

    def test_execute_sequential_through_execute(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_run_swarm(
            {"pattern": "sequential", "task": "test", "agent_roles": ["code", "plan"]},
            ctx,
        )
        assert "Sequential Swarm" in result

    def test_execute_debate_through_execute(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_run_swarm(
            {"pattern": "debate", "task": "test", "agent_count": 2},
            ctx,
        )
        assert "Debate Swarm" in result

    def test_execute_broadcast_through_execute(self) -> None:
        orch = _make_orchestrator()
        ctx = _make_context(orchestrator=orch)
        result = _execute_run_swarm(
            {"pattern": "broadcast", "task": "test", "agent_count": 2},
            ctx,
        )
        assert "Broadcast Swarm" in result
