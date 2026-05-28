from __future__ import annotations

import os
from typing import Any

from tools import Tool, ToolContext

IGNORE_DIRS = frozenset({
    "node_modules", ".git", ".svn", ".hg", "dist", "build", ".next",
    "__pycache__", ".venv", ".claude", ".mypy_cache", ".pytest_cache",
})


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    root_dir = args.get("path") or os.getcwd()
    max_depth = min(int(args.get("depth", 3)), 10)

    lines: list[str] = [root_dir + "/"]

    def walk(current: str, depth: int) -> None:
        if depth > max_depth:
            return

        try:
            entries = sorted(os.scandir(current), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            if entry.name.startswith(".") or entry.name in IGNORE_DIRS:
                continue

            indent = "  " * depth
            if entry.is_dir():
                lines.append(f"{indent}{entry.name}/")
                walk(entry.path, depth + 1)
            else:
                lines.append(f"{indent}{entry.name}")

    walk(root_dir, 1)
    return "\n".join(lines)


directory_tree_tool = Tool(
    name="directory_tree",
    description=(
        "Get a tree view of files and directories. "
        "Shows the structure of a project or directory."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root directory to show (defaults to project root)"},
            "depth": {"type": "number", "description": "Maximum depth to recurse (default: 3, max: 10)"},
        },
    },
    execute=execute,
    read_only=True,
)
