from __future__ import annotations

import os as _os
from typing import Any

from tools import Tool, ToolContext
from src.plan import save_pending_plan
from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    name = args.get("name")
    content = args.get("content")

    if not name or not isinstance(name, str) or not name.strip():
        return 'Error: missing required argument "name".'
    if not content or not isinstance(content, str) or not content.strip():
        return 'Error: missing required argument "content".'

    try:
        name_str = name.strip()
        filepath = save_pending_plan(name_str, content, ctx.working_directory)

        # Post-write verification: confirm the file actually exists on disk.
        # This catches silent failures where the write targeted a different
        # directory than expected (e.g. thread CWD mismatch).
        if not _os.path.isfile(filepath):
            error_msg = (
                f"write_plan reported success but file does not exist at expected path: {filepath}. "
                f"working_directory={ctx.working_directory!r}, cwd={_os.getcwd()!r}"
            )
            logger.error(error_msg)
            return f"Error: {error_msg}"

        logger.info("Plan saved via write_plan tool: name=%s, file=%s", name_str, filepath)
        return f"Plan saved to {filepath}"
    except Exception as exc:
        logger.error("Error saving plan via write_plan: %s", exc)
        return f"Error saving plan: {exc}"


write_plan_tool = Tool(
    name="write_plan",
    description=(
        "Save a plan as a Markdown file in the plans/pending/ directory. "
        "The plan will be stored with YAML front-matter (name, status, created_at). "
        "Use this when you've finished exploring and designing a plan in PLAN mode "
        "and want to persist it for the user to review and approve."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "A short descriptive name for the plan (used as the filename).",
            },
            "content": {
                "type": "string",
                "description": "The full plan content in Markdown format.",
            },
        },
        "required": ["name", "content"],
    },
    execute=execute,
    read_only=True,
)
