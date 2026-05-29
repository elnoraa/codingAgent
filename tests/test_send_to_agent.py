"""Tests for agent-to-agent communication access controls."""

from __future__ import annotations

from src.tools.send_to_agent import _can_communicate


class MockAgent:
    """Minimal mock agent for testing access control."""

    def __init__(self, agent_id: str, parent_id: str | None = None, role: str = "worker"):
        self.agent_id = agent_id
        self.parent_id = parent_id
        self.role = role


class MockOrchestrator:
    """Minimal mock orchestrator for testing access control."""

    def __init__(self) -> None:
        self.agents: dict[str, MockAgent] = {
            "main": MockAgent("main", parent_id=None, role="code"),
        }

    def add_agent(self, agent_id: str, parent_id: str | None = None, role: str = "worker") -> None:
        self.agents[agent_id] = MockAgent(agent_id, parent_id, role)

    def get_agent(self, agent_id: str) -> MockAgent | None:
        return self.agents.get(agent_id)


class TestAgentCommunicationAccessControl:
    """Verify agent communication restrictions."""

    def test_main_can_communicate_with_anyone(self) -> None:
        """The main agent should be able to send messages to any sub-agent."""
        orch = MockOrchestrator()
        orch.add_agent("worker-1", parent_id="main")
        assert _can_communicate(orch, "main", "worker-1", "text") is None

    def test_child_can_talk_to_parent(self) -> None:
        """A sub-agent should be able to send messages to its parent."""
        orch = MockOrchestrator()
        orch.add_agent("worker-1", parent_id="main")
        assert _can_communicate(orch, "worker-1", "main", "text") is None

    def test_child_can_talk_to_sibling(self) -> None:
        """Sibling agents (same parent) should be able to communicate."""
        orch = MockOrchestrator()
        orch.add_agent("worker-1", parent_id="main")
        orch.add_agent("worker-2", parent_id="main")
        assert _can_communicate(orch, "worker-1", "worker-2", "text") is None

    def test_unrelated_agents_blocked(self) -> None:
        """Unrelated agents should not be able to communicate."""
        orch = MockOrchestrator()
        orch.add_agent("worker-1", parent_id="main")
        orch.add_agent("deep-agent", parent_id="worker-1")
        orch.add_agent("other-worker", parent_id="main")

        result = _can_communicate(orch, "deep-agent", "other-worker", "text")
        assert result is not None

    def test_only_parent_can_cancel(self) -> None:
        """Only the parent agent should be able to send cancel messages."""
        orch = MockOrchestrator()
        orch.add_agent("worker-1", parent_id="main")
        orch.add_agent("worker-2", parent_id="main")

        assert _can_communicate(orch, "main", "worker-1", "cancel") is None
        assert _can_communicate(orch, "worker-2", "worker-1", "cancel") is not None

    def test_read_only_agents_cannot_send_instructions(self) -> None:
        """Read-only agents (plan, ask, observer) cannot send instruction messages."""
        orch = MockOrchestrator()
        orch.add_agent("planner", parent_id="main", role="plan")
        orch.add_agent("worker-1", parent_id="main")

        result = _can_communicate(orch, "planner", "worker-1", "instruction")
        assert result is not None

    def test_read_only_agents_can_send_text(self) -> None:
        """Read-only agents should still be able to send text messages."""
        orch = MockOrchestrator()
        orch.add_agent("planner", parent_id="main", role="plan")
        orch.add_agent("worker-1", parent_id="main")

        assert _can_communicate(orch, "planner", "worker-1", "text") is None

    def test_unknown_agent_returns_error(self) -> None:
        """Unknown agents should be rejected."""
        orch = MockOrchestrator()
        result = _can_communicate(orch, "nonexistent", "main", "text")
        assert result is not None

    def test_observer_role_cannot_instruct(self) -> None:
        """Observer role should not be able to instruct."""
        orch = MockOrchestrator()
        orch.add_agent("observer-1", parent_id="main", role="observer")
        orch.add_agent("worker-1", parent_id="main")

        result = _can_communicate(orch, "observer-1", "worker-1", "instruction")
        assert result is not None
