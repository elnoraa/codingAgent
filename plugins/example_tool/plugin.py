"""Example plugin demonstrating the Coding Agent plugin system."""

from __future__ import annotations

from tools import Tool, ToolContext

__version__ = "1.0.0"
__description__ = "Example plugin with a hello world tool"
__author__ = "Coding Agent User"


def hello_tool_execute(args: dict, ctx: ToolContext) -> str:
    name = args.get("name", "World")
    return f"Hello, {name}! (from plugin)"


hello_tool = Tool(
    name="hello",
    description="A friendly greeting tool from the example plugin",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name to greet"},
        },
    },
    execute=hello_tool_execute,
)


def on_startup():
    print("  Example plugin started!")


def on_shutdown():
    print("  Example plugin shutting down!")
