from __future__ import annotations

from typing import Any

from tools import Tool, ToolContext


def execute(_args: dict[str, Any], ctx: ToolContext) -> str:
    ctx.restart_requested = True
    return "Session will be restarted on next turn."


restart_session_tool = Tool(
    name="restart_session",
    description=(
        "Reset the session back to turn 1. Call this AFTER you complete a task "
        "and present a summary of what was done. This clears the conversation "
        "history and restarts the plan-first cycle so the user can begin a new task."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=execute,
    read_only=True,
)
