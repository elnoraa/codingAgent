"""Tool: send_to_agent — send a message or instruction to another agent.

Allows cross-agent communication. The parent agent can send instructions,
data, or cancellation signals to any of its sub-agents.
"""

from __future__ import annotations

import logging

from tools import Tool, ToolContext

logger = logging.getLogger(__name__)


def _execute_send_to_agent(args: dict[str, object], context: ToolContext) -> str:
    """Execute the send_to_agent tool."""
    orchestrator = getattr(context, "orchestrator", None)
    if orchestrator is None:
        return "Error: No orchestrator available."

    agent_id = str(args.get("agent_id", ""))
    if not agent_id:
        return "Error: 'agent_id' parameter is required."

    message = str(args.get("message", ""))
    if not message:
        return "Error: 'message' parameter is required."

    message_type = str(args.get("message_type", "text"))
    if message_type not in ("text", "instruction", "result", "cancel"):
        return (
            f"Error: Unknown message_type '{message_type}'. "
            f"Use: text, instruction, result, or cancel."
        )

    sender_id = getattr(context, "agent_id", "main")

    try:
        confirmation = orchestrator.send_message(
            from_id=sender_id,
            to_id=agent_id,
            content=message,
            message_type=message_type,
        )
        return confirmation
    except Exception as exc:
        logger.error("send_to_agent failed: %s", exc, exc_info=True)
        return f"Error sending message: {exc}"


send_to_agent_tool = Tool(
    name="send_to_agent",
    description=(
        "Send a message or instruction to a running sub-agent. "
        "Use this to delegate work, provide context, or request results."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "The ID of the target agent (from list_agents).",
            },
            "message": {
                "type": "string",
                "description": "The message content to send.",
            },
            "message_type": {
                "type": "string",
                "enum": ["text", "instruction", "result", "cancel"],
                "description": (
                    "Type of message: 'text' for general, "
                    "'instruction' for a task, 'result' to pass data back, "
                    "'cancel' to abort the agent."
                ),
            },
        },
        "required": ["agent_id", "message"],
    },
    execute=_execute_send_to_agent,
    read_only=False,
)
