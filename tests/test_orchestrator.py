"""Tests for the Orchestrator — multi-agent lifecycle and communication."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.client import LlmClient
from src.orchestrator import AgentHandle, Orchestrator
from src.tools import ToolContext

# ── Helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture
def orchestrator() -> Orchestrator:
    """Create an Orchestrator with a mocked LLM client."""
    llm = MagicMock(spec=LlmClient)
    llm.model = "test-model"
    llm.max_tokens = 1024
    llm.temperature = 0.7
    llm.top_p = 1.0
    # Mock the underlying Anthropic client to avoid _get_api_key() failures
    mock_client = MagicMock()
    mock_client.api_key = "sk-test-key"
    mock_client.base_url = "https://test.api.com"
    llm.client = mock_client
    return Orchestrator(
        default_llm=llm,
        default_system_prompt="Test system prompt",
        default_working_directory=".",
    )


@pytest.fixture
def context() -> MagicMock:
    """Create a mock ToolContext."""
    return MagicMock(spec=ToolContext)


# ── Initialization Tests ─────────────────────────────────────────────────────


class TestOrchestratorInitialization:
    """Verify Orchestrator initializes with sensible defaults."""

    def test_init_empty_agents(self, orchestrator: Orchestrator) -> None:
        assert orchestrator._agents == {}

    def test_init_empty_handles(self, orchestrator: Orchestrator) -> None:
        assert orchestrator._handles == {}

    def test_init_empty_parent_map(self, orchestrator: Orchestrator) -> None:
        assert orchestrator._parent_map == {}

    def test_init_stores_llm(self, orchestrator: Orchestrator) -> None:
        assert orchestrator._default_llm.model == "test-model"

    def test_init_stores_system_prompt(self, orchestrator: Orchestrator) -> None:
        assert orchestrator._default_system_prompt == "Test system prompt"

    def test_init_stores_working_directory(self, orchestrator: Orchestrator) -> None:
        assert orchestrator._default_working_directory == "."

    def test_max_nesting_depth_default(self, orchestrator: Orchestrator) -> None:
        assert orchestrator._max_nesting_depth == 3


# ── Spawn Agent Tests ────────────────────────────────────────────────────────


class TestSpawnAgent:
    """Verify agent spawning."""

    def test_spawn_returns_handle(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "do something", role="worker")
        assert isinstance(handle, AgentHandle)

    def test_spawn_sets_role(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "task", role="plan")
        assert handle.role == "plan"

    def test_spawn_sets_status_idle(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "task", role="worker")
        assert handle.status == "idle"

    def test_spawn_adds_to_registry(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "task", role="worker")
        assert handle.agent_id in orchestrator._agents
        assert handle.agent_id in orchestrator._handles

    def test_spawn_generates_unique_ids(self, orchestrator: Orchestrator) -> None:
        h1 = orchestrator.spawn_agent(None, "task1")
        h2 = orchestrator.spawn_agent(None, "task2")
        assert h1.agent_id != h2.agent_id

    def test_spawn_sets_message_count(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "initial task")
        assert handle.message_count >= 1

    def test_spawn_tracks_created_at(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "task")
        assert handle.created_at > 0

    def test_spawn_with_model_override(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(
            None,
            "task",
            model="claude-3-opus",
            max_tokens=8192,
        )
        agent = orchestrator._agents[handle.agent_id]
        assert agent.config.llm.model == "claude-3-opus"
        assert agent.config.max_tokens == 8192

    def test_spawn_parent_child_relationship(self, orchestrator: Orchestrator) -> None:
        parent = orchestrator.spawn_agent(None, "parent")
        child = orchestrator.spawn_agent(parent.agent_id, "child")
        assert orchestrator._parent_map[child.agent_id] == parent.agent_id

    def test_spawn_enforces_nesting_depth(self, orchestrator: Orchestrator) -> None:
        """Nesting beyond max depth should raise RuntimeError.

        Max depth is 3, so chain of 4 agents (root → child → grandchild → great-grandchild)
        should fail when spawning the 5th level.
        """
        a1 = orchestrator.spawn_agent(None, "level1", role="worker")  # depth=0
        a2 = orchestrator.spawn_agent(a1.agent_id, "level2", role="worker")  # depth=1
        a3 = orchestrator.spawn_agent(a2.agent_id, "level3", role="worker")  # depth=2
        a4 = orchestrator.spawn_agent(a3.agent_id, "level4", role="worker")  # depth=3 — should fail
        with pytest.raises(RuntimeError, match="nesting depth"):
            orchestrator.spawn_agent(a4.agent_id, "too deep", role="worker")


# ── Run Agent Tests ──────────────────────────────────────────────────────────


class TestRunAgent:
    """Verify agent execution."""

    def test_run_agent_updates_status(self, orchestrator: Orchestrator, context: MagicMock) -> None:
        handle = orchestrator.spawn_agent(None, "do something", role="worker")
        result = orchestrator.run_agent(handle.agent_id, context, "execute this")
        # After running, status should be something other than idle
        assert handle.status in ("completed", "error")

    def test_run_agent_returns_result(self, orchestrator: Orchestrator, context: MagicMock) -> None:
        handle = orchestrator.spawn_agent(None, "task", role="worker")
        result = orchestrator.run_agent(handle.agent_id, context, "do it")
        assert result is not None
        assert hasattr(result, "output") or hasattr(result, "summary")

    def test_run_nonexistent_agent_raises(self, orchestrator: Orchestrator, context: MagicMock) -> None:
        with pytest.raises(ValueError, match="Unknown agent"):
            orchestrator.run_agent("nonexistent-id", context, "task")


# ── Terminate Agent Tests ────────────────────────────────────────────────────


class TestTerminateAgent:
    """Verify agent termination."""

    def test_terminate_removes_agent(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "task")
        assert handle.agent_id in orchestrator._agents
        orchestrator.terminate_agent(handle.agent_id)
        assert handle.agent_id not in orchestrator._agents

    def test_terminate_removes_handle(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "task")
        assert handle.agent_id in orchestrator._handles
        orchestrator.terminate_agent(handle.agent_id)
        assert handle.agent_id not in orchestrator._handles

    def test_terminate_removes_parent_mapping(self, orchestrator: Orchestrator) -> None:
        parent = orchestrator.spawn_agent(None, "parent")
        child = orchestrator.spawn_agent(parent.agent_id, "child")
        orchestrator.terminate_agent(child.agent_id)
        assert child.agent_id not in orchestrator._parent_map

    def test_terminate_nonexistent_agent(self, orchestrator: Orchestrator) -> None:
        """Should not crash when terminating a non-existent agent."""
        orchestrator.terminate_agent("nonexistent")  # Should not raise

    def test_terminate_does_not_remove_other_agents(self, orchestrator: Orchestrator) -> None:
        h1 = orchestrator.spawn_agent(None, "task1")
        h2 = orchestrator.spawn_agent(None, "task2")
        orchestrator.terminate_agent(h1.agent_id)
        assert h2.agent_id in orchestrator._agents


# ── List Agents Tests ────────────────────────────────────────────────────────


class TestListAgents:
    """Verify agent listing."""

    def test_list_empty(self, orchestrator: Orchestrator) -> None:
        handles = orchestrator.list_agents()
        assert handles == []

    def test_list_returns_all(self, orchestrator: Orchestrator) -> None:
        h1 = orchestrator.spawn_agent(None, "task1")
        h2 = orchestrator.spawn_agent(None, "task2")
        handles = orchestrator.list_agents()
        assert len(handles) == 2
        ids = [h.agent_id for h in handles]
        assert h1.agent_id in ids
        assert h2.agent_id in ids

    def test_list_after_terminate(self, orchestrator: Orchestrator) -> None:
        h1 = orchestrator.spawn_agent(None, "task1")
        h2 = orchestrator.spawn_agent(None, "task2")
        orchestrator.terminate_agent(h1.agent_id)
        handles = orchestrator.list_agents()
        assert len(handles) == 1
        assert handles[0].agent_id == h2.agent_id


# ── Send Message Tests ───────────────────────────────────────────────────────


class TestSendMessage:
    """Verify inter-agent communication."""

    def test_send_message_adds_to_recipient(self, orchestrator: Orchestrator) -> None:
        sender = orchestrator.spawn_agent(None, "sender", role="worker")
        recipient = orchestrator.spawn_agent(None, "recipient", role="worker")
        orchestrator.send_message(sender.agent_id, recipient.agent_id, "hello from sender")
        agent = orchestrator._agents[recipient.agent_id]
        assert any("hello" in str(m.get("content", "")) for m in agent.messages)

    def test_send_message_nonexistent_target(self, orchestrator: Orchestrator) -> None:
        sender = orchestrator.spawn_agent(None, "sender")
        result = orchestrator.send_message(sender.agent_id, "nonexistent", "hello")
        assert "error" in result.lower() or "unknown" in result.lower()

    def test_send_message_nonexistent_sender(self, orchestrator: Orchestrator) -> None:
        recipient = orchestrator.spawn_agent(None, "recipient")
        result = orchestrator.send_message("unknown-sender", recipient.agent_id, "hello")
        assert "error" not in result.lower()


# ── Get Agent Handle Tests (via list_agents) ─────────────────────────────────


class TestAgentHandleRetrieval:
    """Verify retrieving agent information."""

    def test_handle_via_list(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "task")
        handles = orchestrator.list_agents()
        matching = [h for h in handles if h.agent_id == handle.agent_id]
        assert len(matching) == 1
        assert matching[0].role == handle.role

    def test_handle_after_terminate_removed_from_list(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "task")
        orchestrator.terminate_agent(handle.agent_id)
        handles = orchestrator.list_agents()
        assert not any(h.agent_id == handle.agent_id for h in handles)


# ── Nesting Depth Helper Tests ───────────────────────────────────────────────


class TestNestingDepth:
    """Verify the _get_depth helper."""

    def test_depth_zero_for_no_parent(self, orchestrator: Orchestrator) -> None:
        handle = orchestrator.spawn_agent(None, "task")
        depth = orchestrator._get_depth(handle.agent_id)
        assert depth == 0

    def test_depth_one_for_child(self, orchestrator: Orchestrator) -> None:
        parent = orchestrator.spawn_agent(None, "parent")
        child = orchestrator.spawn_agent(parent.agent_id, "child")
        depth = orchestrator._get_depth(child.agent_id)
        assert depth == 1

    def test_depth_none_returns_zero(self, orchestrator: Orchestrator) -> None:
        depth = orchestrator._get_depth(None)
        assert depth == 0

    def test_depth_unknown_returns_zero(self, orchestrator: Orchestrator) -> None:
        depth = orchestrator._get_depth("nonexistent")
        assert depth == 0
