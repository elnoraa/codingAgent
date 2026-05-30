from __future__ import annotations

import os as _os
from typing import Any

from src.logging_config import get_logger
from src.plan import update_pending_plan
from src.tools import Tool, ToolContext

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
        filepath = update_pending_plan(name_str, content, ctx.working_directory)

        # Post-write verification: confirm the file actually exists on disk.
        if not _os.path.isfile(filepath):
            error_msg = (
                f"edit_plan reported success but file does not exist at expected path: {filepath}. "
                f"working_directory={ctx.working_directory!r}, cwd={_os.getcwd()!r}"
            )
            logger.error(error_msg)
            return f"Error: {error_msg}"

        logger.info("Plan updated via edit_plan tool: name=%s, file=%s", name_str, filepath)
        return f"Plan updated: {filepath}"
    except FileNotFoundError as exc:
        logger.warning("Plan not found for edit: name=%s", name)
        return f"Error: {exc}"
    except Exception as exc:
        logger.error("Error updating plan via edit_plan: %s", exc)
        return f"Error updating plan: {exc}"


edit_plan_tool = Tool(
    name="edit_plan",
    description=(
        "Update an existing plan in the plans/pending/ directory. "
        "Preserves the YAML front-matter (name, status, created_at) and replaces "
        "the body content with the provided Markdown. "
        "Use this to refine or update a plan that already exists, "
        "rather than creating a duplicate with write_plan."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "The plan name (filename stem, with or without the numeric prefix). "
                    "Examples: '05-feat-add-login', 'feat-add-login', or '73-feat-enforce-read-only-by-mode'."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "The new full plan content in Markdown format. "
                    "Do NOT include YAML front-matter — it will be preserved automatically."
                ),
            },
        },
        "required": ["name", "content"],
    },
    execute=execute,
    read_only=True,
)
