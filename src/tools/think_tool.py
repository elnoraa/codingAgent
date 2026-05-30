from __future__ import annotations

from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def execute(_args: dict[str, Any], _ctx: ToolContext) -> str:
    logger.info("execute: think tool called")
    return "Thinking..."


think_tool = Tool(
    name="think",
    description=(
        "A no-op tool that lets you 'think' or reason through a problem step by "
        "step without taking any action. Use this to break down complex problems, "
        "plan your approach, or explain your reasoning before executing tools. "
        "This tool does nothing and returns immediately."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=execute,
    read_only=True,
)
