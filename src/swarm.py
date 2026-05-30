"""Swarm execution types for the Coding Agent.

Provides the ``SwarmResult`` dataclass used by swarm execution functions.

Extracted from ``src/orchestrator.py`` to separate swarm concerns from
agent lifecycle management (Single Responsibility Principle).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agent import AgentResult


@dataclass
class SwarmResult:
    """Result from a swarm execution."""

    pattern: str
    task: str
    agent_results: list[AgentResult] = field(default_factory=list)
    summary: str = ""
    error: str | None = None
