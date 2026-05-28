"""Tool: list_agents — list all active sub-agents and their status.

Returns a readable summary of every agent managed by the orchestrator,
including their ID, role, status, message count, and (if completed) a
preview of their result.
"""

from __future__ import annotations

import logging

from tools import Tool, ToolContext

logger = logging.getLogger(__name__)


def _execute_list_agents(args: dict[str, object], context: ToolContext) -> str:
    """Execute the list_agents tool."""
    orchestrator = getattr(context, "orchestrator", None)
    if orchestrator is None:
        return "Error: No orchestrator available."

    agent_id = getattr(context, "agent_id", "main")
    handles = orchestrator.list_agents(parent_id=agent_id)

    if not handles:
        return "No sub-agents found."

    lines: list[str] = []
    lines.append(f"**Sub-Agents ({len(handles)} total)**")
    lines.append("")

    for h in handles:
        status_icon = {
            "idle": "○",
            "running": "⟳",
            "completed": "✓",
            "error": "✗",
        }.get(h.status, "?")

        lines.append(
            f"  {status_icon} **{h.agent_id}** "
            f"(role: {h.role}, status: {h.status}, "
            f"messages: {h.message_count})"
        )

        if h.result:
            preview = (
                h.result.summary[:120] if h.result.summary
                else h.result.output[:120]
            )
            if preview:
                lines.append(f"       ↳ {preview}")
            if h.result.error:
                lines.append(f"       ⚠ Error: {h.result.error[:120]}")

    lines.append("")
    lines.append("Use `send_to_agent` to communicate with an agent.")
    return "\n".join(lines)


list_agents_tool = Tool(
    name="list_agents",
    description=(
        "List all active sub-agents with their ID, role, status, "
        "message count, and result preview."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=_execute_list_agents,
    read_only=True,
)
