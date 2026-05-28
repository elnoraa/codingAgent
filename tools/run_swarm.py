"""Tool: run_swarm — run a swarm of agents in a collaboration pattern.

Supports patterns:
- sequential: agents run one after another, passing results forward
- debate: multiple agents independently solve, then compare
- broadcast: multiple agents independently solve, best result wins
"""

from __future__ import annotations

import threading
import time
from typing import Any

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)

# ── Swarm pattern implementations ─────────────────────────────────────────────


def _run_sequential_swarm(
    orchestrator: Any,
    parent_id: str,
    task: str,
    agent_roles: list[str],
    context: ToolContext,
) -> str:
    """Run agents sequentially, passing results forward."""
    lines: list[str] = [
        f"**Sequential Swarm** — {len(agent_roles)} agent(s)",
        "",
    ]
    current_task = task
    results: list[str] = []

    for i, role in enumerate(agent_roles):
        agent_task = (
            f"{current_task}\n\nContext from previous step:\n{results[-1] if results else 'N/A'}"
            if i > 0 else current_task
        )
        lines.append(f"**Step {i + 1}:** Spawning {role} agent...")

        try:
            handle = orchestrator.spawn_agent(
                parent_id=parent_id,
                task=agent_task,
                role=role,
            )
            agent_id = handle.agent_id
            lines.append(f"  Agent ID: {agent_id}")

            agent_result = orchestrator.run_agent(agent_id, context)
            if agent_result.error:
                lines.append(f"  ⚠ Error: {agent_result.error}")
                break

            preview = (
                agent_result.output[:300] if agent_result.output
                else "(no output)"
            )
            lines.append(f"  Result: {preview}")
            results.append(agent_result.output)

            orchestrator.terminate_agent(agent_id)
        except Exception as exc:
            lines.append(f"  ⚠ Exception: {exc}")
            break

    lines.append("")
    lines.append("**Swarm complete.**")
    return "\n".join(lines)


def _run_debate_swarm(
    orchestrator: Any,
    parent_id: str,
    task: str,
    agent_count: int,
    context: ToolContext,
) -> str:
    """Run multiple agents independently on the same task, then compare."""
    lines: list[str] = [
        f"**Debate Swarm** — {agent_count} agent(s), same task",
        f"**Task:** {task}",
        "",
    ]

    results: list[tuple[str, str, float]] = []  # (agent_id, output, tokens)

    def _run_debater(idx: int) -> tuple[str, str, float] | None:
        """Run a single debater agent."""
        try:
            handle = orchestrator.spawn_agent(
                parent_id=parent_id,
                task=task,
                role="code",
            )
            agent_id = handle.agent_id
            agent_result = orchestrator.run_agent(agent_id, context)
            output = agent_result.output or "(no output)"
            tokens = agent_result.input_tokens + agent_result.output_tokens
            orchestrator.terminate_agent(agent_id)
            return (agent_id, output, tokens)
        except Exception as exc:
            logger.error("Debater %d failed: %s", idx, exc)
            return None

    # Run debaters concurrently using threads
    threads: list[threading.Thread] = []
    collected: list[tuple[str, str, float] | None] = [None] * agent_count

    def _worker(idx: int) -> None:
        collected[idx] = _run_debater(idx)

    for i in range(agent_count):
        t = threading.Thread(target=_worker, args=(i,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=300)  # 5-minute timeout per debater

    # Collect and compare
    for i, result in enumerate(collected):
        if result is None:
            lines.append(f"**Debater {i + 1}:** ❌ Failed/Timed out")
        else:
            agent_id, output, tokens = result
            lines.append(f"**Debater {i + 1}** ({agent_id}, ~{int(tokens)} tokens):")
            lines.append(f"  {output[:200]}")
            results.append((agent_id, output, tokens))
        lines.append("")

    # Synthesize comparison
    if len(results) >= 2:
        lines.append("**Comparison:**")
        lines.append(f"  {len(results)} debaters completed.")
        # Pick the longest output as a simple heuristic for most thorough
        best = max(results, key=lambda r: len(r[1]))
        lines.append(f"  Most thorough: {best[0]} ({len(best[1])} chars)")
        lines.append("")

    lines.append("**Debate complete.**")
    return "\n".join(lines)


def _run_broadcast_swarm(
    orchestrator: Any,
    parent_id: str,
    task: str,
    agent_count: int,
    context: ToolContext,
) -> str:
    """Run N agents independently, return the best result."""
    lines: list[str] = [
        f"**Broadcast Swarm** — {agent_count} agent(s)",
        f"**Task:** {task}",
        "",
    ]

    results: list[tuple[str, str, float]] = []

    for i in range(agent_count):
        try:
            handle = orchestrator.spawn_agent(
                parent_id=parent_id,
                task=task,
                role="code",
            )
            agent_id = handle.agent_id
            lines.append(f"**Worker {i + 1}** ({agent_id})...")

            agent_result = orchestrator.run_agent(agent_id, context)
            output = agent_result.output or "(no output)"
            tokens = agent_result.input_tokens + agent_result.output_tokens
            preview = output[:200]
            lines.append(f"  Result: {preview}")
            results.append((agent_id, output, tokens))

            orchestrator.terminate_agent(agent_id)
        except Exception as exc:
            lines.append(f"  ⚠ Worker {i + 1} failed: {exc}")

    if results:
        # Best result = longest output (simple heuristic)
        best = max(results, key=lambda r: len(r[1]))
        lines.append("")
        lines.append(f"**Best result** from {best[0]} ({len(best[1])} chars):")
        lines.append(f"  {best[1][:500]}")

    lines.append("")
    lines.append("**Broadcast complete.**")
    return "\n".join(lines)


# ── Tool executor ─────────────────────────────────────────────────────────────


def _execute_run_swarm(args: dict[str, object], context: ToolContext) -> str:
    """Execute the run_swarm tool."""
    orchestrator = getattr(context, "orchestrator", None)
    if orchestrator is None:
        return "Error: No orchestrator available."

    pattern = str(args.get("pattern", ""))
    if not pattern:
        return "Error: 'pattern' parameter is required."

    task = str(args.get("task", ""))
    if not task:
        return "Error: 'task' parameter is required."

    agent_id = getattr(context, "agent_id", "main")
    agent_roles = args.get("agent_roles", None)
    agent_count = int(str(args.get("agent_count", 2)))

    try:
        if pattern == "sequential":
            roles: list[str] = []
            if isinstance(agent_roles, list):
                roles = [str(r) for r in agent_roles]
            if not roles:
                roles = ["code", "code", "code"]
            return _run_sequential_swarm(orchestrator, agent_id, task, roles, context)

        elif pattern == "debate":
            count = max(2, agent_count)
            return _run_debate_swarm(orchestrator, agent_id, task, count, context)

        elif pattern == "broadcast":
            count = max(2, agent_count)
            return _run_broadcast_swarm(orchestrator, agent_id, task, count, context)

        else:
            return (
                f"Error: Unknown swarm pattern '{pattern}'. "
                f"Available: sequential, debate, broadcast."
            )

    except Exception as exc:
        logger.error("run_swarm failed: %s", exc, exc_info=True)
        return f"Error running swarm: {exc}"


run_swarm_tool = Tool(
    name="run_swarm",
    description=(
        "Run a swarm of agents in a collaboration pattern. "
        "'sequential': agents run in order, passing results forward. "
        "'debate': multiple agents independently solve the same task, then compare. "
        "'broadcast': multiple agents work independently, best result wins."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "enum": ["sequential", "debate", "broadcast"],
                "description": "Swarm collaboration pattern.",
            },
            "task": {
                "type": "string",
                "description": "The overall task for the swarm.",
            },
            "agent_roles": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Roles for each agent (for sequential pattern). "
                    "Example: ['planner', 'implementer', 'reviewer']"
                ),
            },
            "agent_count": {
                "type": "integer",
                "description": "Number of agents (for debate/broadcast patterns, default: 2).",
            },
        },
        "required": ["pattern", "task"],
    },
    execute=_execute_run_swarm,
    read_only=False,
)
