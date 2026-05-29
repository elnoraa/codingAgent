"""Tool: send_to_agent — send a message or instruction to another agent.

Allows cross-agent communication. The parent agent can send instructions,
data, or cancellation signals to any of its sub-agents.
"""

from __future__ import annotations

from typing import Any

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)


def _can_communicate(
    orchestrator: Any,
    from_id: str,
    to_id: str,
    message_type: str,
) -> str | None:
    """Check if agent *from_id* is allowed to send a message to *to_id*.

    Rules:
    1. The main agent can communicate with any sub-agent.
    2. A sub-agent can only communicate with its direct parent or siblings
       (agents sharing the same parent), but not with arbitrary agents.
    3. Only the parent agent (or main) can send 'cancel' messages.
    4. Read-only agents cannot send 'instruction' messages.

    Returns ``None`` if allowed, or an error message if denied.
    """
    # Main agent can always communicate
    if from_id == "main":
        return None

    try:
        from_agent = orchestrator.get_agent(from_id)
        to_agent = orchestrator.get_agent(to_id)
    except (KeyError, AttributeError):
        return f"Error: Unknown agent '{from_id}' or '{to_id}'."

    if from_agent is None or to_agent is None:
        return f"Error: Unknown agent '{from_id}' or '{to_id}'."

    from_parent = getattr(from_agent, 'parent_id', None) if from_agent else None
    to_parent = getattr(to_agent, 'parent_id', None) if to_agent else None

    # Agents can talk to their own parent, children, or siblings
    if to_parent == from_id or from_parent == to_id:
        pass  # Parent-child communication
    elif from_parent is not None and from_parent == to_parent:
        pass  # Sibling communication
    elif to_id == "main":
        pass  # Agent can talk to main
    else:
        return (
            f"Error: Agent '{from_id}' is not allowed to send messages "
            f"to agent '{to_id}'. Agents can only communicate with their "
            f"parent, direct children, or siblings (same parent)."
        )

    # Only the parent (or main) can send 'cancel'
    if message_type == "cancel" and from_id != "main" and from_parent != to_id:
        return (
            f"Error: Agent '{from_id}' is not allowed to cancel agent "
            f"'{to_id}'. Only the parent agent can send cancel messages."
        )

    # Check if the sending agent is read-only
    from_role = getattr(from_agent, 'role', None) if from_agent else None
    if from_role in ("plan", "ask", "observer") and message_type == "instruction":
        return (
            f"Error: Agent '{from_id}' has role '{from_role}' which is "
            f"read-only and cannot send 'instruction' messages."
        )

    return None


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

    # ── Access control ──────────────────────────────────────────────────
    access_error = _can_communicate(
        orchestrator, sender_id, agent_id, message_type,
    )
    if access_error:
        return access_error

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
