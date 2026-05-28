from __future__ import annotations

from typing import Any

from tools import Tool, ToolContext
from src.plan import complete_plan
from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    name = args.get("name")

    if not name or not isinstance(name, str) or not name.strip():
        return 'Error: missing required argument "name".'

    try:
        name_str = name.strip()
        success = complete_plan(name_str, ctx.working_directory)
        if success:
            ctx.restart_requested = True
            logger.info(
                "Plan completed via complete_plan tool: name=%s (restart scheduled)",
                name_str,
            )
            return (
                f"Plan '{name_str}' moved from plans/pending/ to plans/completed/. "
                f"The session will restart on the next turn."
            )
        return f'Error: plan "{name_str}" not found in plans/pending/. Use write_plan first or check the name.'
    except Exception as exc:
        logger.error("Error completing plan via complete_plan tool: %s", exc)
        return f"Error completing plan: {exc}"


complete_plan_tool = Tool(
    name="complete_plan",
    description=(
        "Complete a plan and restart the session for the next task. "
        "Moves a plan from plans/pending/ to plans/completed/, updates the "
        "YAML front-matter with status: completed and a completed_at timestamp, "
        "then resets the session back to turn 1. "
        "Call this after finishing implementation of a pending plan."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "The name of the plan to complete (the filename stem, "
                    "e.g. 'my-feature' for plans/pending/my-feature.md)."
                ),
            },
        },
        "required": ["name"],
    },
    execute=execute,
    read_only=True,
)
