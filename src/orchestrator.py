"""Orchestrator — manages multiple agent instances, communication, and swarms.

The ``Orchestrator`` is the central registry for all ``Agent`` instances in a
session.  It tracks parent/child relationships, provides communication channels
between agents, and runs pre-defined swarm patterns.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .agent import Agent, AgentConfig, AgentResult
from .client import LlmClient
from tools import ToolContext
from .logging_config import get_logger

logger = get_logger(__name__)


# ── Data types ─────────────────────────────────────────────────────────────────


@dataclass
class AgentHandle:
    """A public handle (reference) to a managed agent."""

    agent_id: str
    role: str
    mode: str
    status: str  # "idle" | "running" | "completed" | "error"
    message_count: int = 0
    result: AgentResult | None = None
    parent_id: str | None = None
    created_at: float = 0.0


@dataclass
class SwarmResult:
    """Result from a swarm execution."""

    pattern: str
    task: str
    agent_results: list[AgentResult] = field(default_factory=list)
    summary: str = ""
    error: str | None = None


# ── Orchestrator class ─────────────────────────────────────────────────────────


class Orchestrator:
    """Central registry and coordinator for all agent instances."""

    def __init__(
        self,
        default_llm: LlmClient,
        default_system_prompt: str,
        default_working_directory: str = ".",
    ) -> None:
        self._default_llm = default_llm
        self._default_system_prompt = default_system_prompt
        self._default_working_directory = default_working_directory
        self._agents: dict[str, Agent] = {}
        self._handles: dict[str, AgentHandle] = {}
        self._parent_map: dict[str, str] = {}  # child_id -> parent_id
        self._max_nesting_depth = 3
        logger.info(
            "Orchestrator initialized (default_llm=%s)", default_llm.model
        )

    # ── Agent lifecycle ───────────────────────────────────────────────────

    def spawn_agent(
        self,
        parent_id: str | None,
        task: str,
        *,
        role: str = "worker",
        model: str | None = None,
        max_tokens: int | None = None,
        tools: Any = None,
    ) -> AgentHandle:
        """Create a new sub-agent and return a handle to it.

        Parameters
        ----------
        parent_id:
            The ID of the parent agent, or ``None`` for a top-level agent.
        task:
            Initial task/message for the new agent.
        role:
            Agent role: ``"code"``, ``"plan"``, ``"ask"``, ``"worker"``,
            or ``"observer"``.
        model:
            Optional model override.  Defaults to the orchestrator's LLM.
        max_tokens:
            Optional max-tokens override.
        tools:
            Optional pre-configured ``ToolRegistry``.  If ``None`` a minimal
            registry is created based on the role.

        Returns
        -------
        AgentHandle
            A handle the parent can use to communicate with the sub-agent.
        """
        # ── Enforce nesting depth ─────────────────────────────────────────
        depth = self._get_depth(parent_id)
        if depth >= self._max_nesting_depth:
            raise RuntimeError(
                f"Maximum agent nesting depth ({self._max_nesting_depth}) "
                f"exceeded. Cannot spawn sub-agent from depth {depth}."
            )

        # ── Generate a unique ID ───────────────────────────────────────────
        agent_id = f"sub-{uuid.uuid4().hex[:8]}"
        created_at = time.time()

        # ── Build config ───────────────────────────────────────────────────
        llm = self._default_llm
        if model and model != self._default_llm.model:
            llm = LlmClient(
                api_key=self._get_api_key(),
                base_url=self._get_base_url(),
                model=model,
                max_tokens=max_tokens or self._default_llm.max_tokens,
                temperature=self._default_llm.temperature,
                top_p=self._default_llm.top_p,
            )

        config = AgentConfig(
            llm=llm,
            system_prompt=self._default_system_prompt,
            max_tokens=max_tokens or self._default_llm.max_tokens,
            mode="plan" if role in ("plan", "observer") else "code",
            working_directory=self._default_working_directory,
            role=role,
            tools=tools,
        )

        # ── Create the agent ───────────────────────────────────────────────
        agent = Agent(agent_id=agent_id, config=config)
        agent.send_message(task, role="user")

        self._agents[agent_id] = agent
        self._handles[agent_id] = AgentHandle(
            agent_id=agent_id,
            role=role,
            mode=config.mode,
            status="idle",
            message_count=1,
            parent_id=parent_id,
            created_at=created_at,
        )
        if parent_id is not None:
            self._parent_map[agent_id] = parent_id

        logger.info(
            "Spawed sub-agent: id=%s, role=%s, parent=%s",
            agent_id, role, parent_id,
        )
        return self._handles[agent_id]

    def get_agent(self, agent_id: str) -> Agent | None:
        """Return the ``Agent`` instance by ID, or ``None``."""
        return self._agents.get(agent_id)

    def get_handle(self, agent_id: str) -> AgentHandle | None:
        """Return the public handle for an agent, or ``None``."""
        return self._handles.get(agent_id)

    def list_agents(
        self, parent_id: str | None = None, *, include_children: bool = True
    ) -> list[AgentHandle]:
        """List all agent handles, optionally filtered by parent.

        Parameters
        ----------
        parent_id:
            If set, only return agents whose parent matches.  Pass ``None``
            to return all top-level agents.
        include_children:
            If True (default), recursively include all descendants.

        Returns
        -------
        list[AgentHandle]
        """
        if parent_id is None and include_children:
            return list(self._handles.values())

        if parent_id is not None:
            children: list[AgentHandle] = []
            for child_id, pid in self._parent_map.items():
                if pid == parent_id:
                    children.append(self._handles[child_id])
                    if include_children:
                        children.extend(self.list_agents(child_id))
            return children

        return list(self._handles.values())

    def terminate_agent(self, agent_id: str) -> bool:
        """Remove an agent and all its children.  Returns True on success."""
        if agent_id not in self._agents:
            logger.warning("Agent not found for termination: %s", agent_id)
            return False

        # Recursively terminate children first
        children = [
            cid for cid, pid in self._parent_map.items() if pid == agent_id
        ]
        for child_id in children:
            self.terminate_agent(child_id)

        del self._agents[agent_id]
        if agent_id in self._handles:
            self._handles[agent_id].status = "completed"
            del self._handles[agent_id]
        self._parent_map.pop(agent_id, None)

        logger.info("Terminated agent: %s", agent_id)
        return True

    # ── Agent execution ───────────────────────────────────────────────────

    def run_agent(
        self,
        agent_id: str,
        tool_context: ToolContext,
        user_input: str | None = None,
    ) -> AgentResult:
        """Run an agent's LLM loop and update its handle with results.

        Parameters
        ----------
        agent_id:
            The agent to run.
        tool_context:
            Shared tool execution context.
        user_input:
            Optional additional input to send before running.  If ``None``,
            the agent's existing messages are used.

        Returns
        -------
        AgentResult
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_id}")

        handle = self._handles[agent_id]
        handle.status = "running"

        if user_input:
            agent.send_message(user_input, role="user")
            handle.message_count += 1

        result = agent.run(user_input or "", tool_context)

        # Update handle with results
        handle.status = "completed" if result.error is None else "error"
        handle.result = result
        handle.message_count = len(agent.messages)

        return result

    # ── Communication ─────────────────────────────────────────────────────

    def send_message(
        self,
        from_id: str,
        to_id: str,
        content: str,
        message_type: str = "text",
    ) -> str:
        """Send a structured message from one agent to another.

        Parameters
        ----------
        from_id:
            Sender agent ID.
        to_id:
            Recipient agent ID.
        content:
            Message text.
        message_type:
            Type hint: ``"text"``, ``"instruction"``, ``"result"``, or ``"cancel"``.

        Returns
        -------
        str
            Confirmation or error message.
        """
        target = self._agents.get(to_id)
        if target is None:
            return f"Error: unknown target agent '{to_id}'"

        sender = self._agents.get(from_id)
        sender_name = sender.agent_id if sender else from_id

        # Prepend type metadata for structured delivery
        full_content = f"[{message_type} from {sender_name}]\n{content}"
        target.send_message(full_content, role="user")

        handle = self._handles.get(to_id)
        if handle is not None:
            handle.message_count = len(target.messages)

        logger.debug(
            "Message sent: from=%s, to=%s, type=%s",
            from_id, to_id, message_type,
        )
        return f"Message sent to agent '{to_id}'."

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_depth(self, agent_id: str | None) -> int:
        """Compute the nesting depth of an agent in the parent tree."""
        depth = 0
        current = agent_id
        while current is not None and current in self._parent_map:
            depth += 1
            current = self._parent_map.get(current)
        return depth

    def _get_api_key(self) -> str:
        """Return the API key from the default LLM client."""
        return getattr(self._default_llm.client, "api_key", "")

    def _get_base_url(self) -> str:
        """Return the base URL from the default LLM client."""
        return getattr(self._default_llm.client, "base_url", "")
