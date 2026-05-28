"""Tool: spawn_agent — create a sub-agent to complete a task.

The LLM can use this tool to delegate work to a child agent. The child agent
runs independently with its own message history and tools.
"""

from __future__ import annotations

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)


def _execute_spawn_agent(args: dict[str, object], context: ToolContext) -> str:
    """Execute the spawn_agent tool."""
    orchestrator = getattr(context, "orchestrator", None)
    if orchestrator is None:
        return "Error: No orchestrator available. Cannot spawn agents in this context."

    task = str(args.get("task", ""))
    if not task:
        return "Error: 'task' parameter is required."

    role = str(args.get("role", "worker"))
    if role not in ("code", "plan", "ask", "worker", "observer"):
        return f"Error: Unknown role '{role}'. Use: code, plan, ask, worker, or observer."

    model = str(args.get("model", "")) or None

    try:
        agent_id = getattr(context, "agent_id", "main")
        handle = orchestrator.spawn_agent(
            parent_id=agent_id,
            task=task,
            role=role,
            model=model,
        )
        return (
            f"✅ Spawed sub-agent **{handle.agent_id}** (role: {role}).\n\n"
            f"**Task:** {task}\n\n"
            f"Use `list_agents` to check its status and `send_to_agent` to "
            f"communicate with it. "
            f"When it's done, use `terminate_agent` to clean up."
        )
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.error("spawn_agent failed: %s", exc, exc_info=True)
        return f"Error spawning agent: {exc}"


spawn_agent_tool = Tool(
    name="spawn_agent",
    description=(
        "Spawn a sub-agent to complete a task. "
        "The sub-agent runs independently with its own message history. "
        "Use list_agents to check status, send_to_agent to communicate, "
        "and terminate_agent to clean up when done."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task for the sub-agent to complete.",
            },
            "role": {
                "type": "string",
                "enum": ["code", "plan", "ask", "worker", "observer"],
                "description": (
                    "Agent role. 'code'=full access, 'plan'=read-only, "
                    "'ask'=Q&A only, 'worker'=full access but can't spawn, "
                    "'observer'=read-only only."
                ),
            },
            "model": {
                "type": "string",
                "description": "Optional: override the LLM model for this agent.",
            },
        },
        "required": ["task"],
    },
    execute=_execute_spawn_agent,
    read_only=False,
)
