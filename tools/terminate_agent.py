"""Tool: terminate_agent — stop and remove a running sub-agent.

Cleans up an agent and all its children from the orchestrator.
"""

from __future__ import annotations

import logging

from tools import Tool, ToolContext

logger = logging.getLogger(__name__)


def _execute_terminate_agent(args: dict[str, object], context: ToolContext) -> str:
    """Execute the terminate_agent tool."""
    orchestrator = getattr(context, "orchestrator", None)
    if orchestrator is None:
        return "Error: No orchestrator available."

    agent_id = str(args.get("agent_id", ""))
    if not agent_id:
        return "Error: 'agent_id' parameter is required."

    try:
        success = orchestrator.terminate_agent(agent_id)
        if success:
            return f"Agent '{agent_id}' and its children have been terminated."
        return f"Error: Agent '{agent_id}' not found."
    except Exception as exc:
        logger.error("terminate_agent failed: %s", exc, exc_info=True)
        return f"Error terminating agent: {exc}"


terminate_agent_tool = Tool(
    name="terminate_agent",
    description=(
        "Stop and remove a sub-agent and all its children. "
        "Use this to clean up completed or stuck agents."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "The ID of the agent to terminate.",
            },
        },
        "required": ["agent_id"],
    },
    execute=_execute_terminate_agent,
    read_only=False,
)
