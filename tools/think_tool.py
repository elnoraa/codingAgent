from __future__ import annotations

from typing import Any

from tools import Tool, ToolContext


def execute(_args: dict[str, Any], _ctx: ToolContext) -> str:
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
