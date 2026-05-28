from __future__ import annotations

import os
from typing import Any, cast

from tools import Tool, ToolContext

MAX_LINES = 1000


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    path = args.get("path")
    if not path:
        return 'Error: missing required argument "path".'

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        parent = os.path.dirname(path)
        try:
            items: list[str] = []
            for raw in cast("list[str]", os.listdir(parent)):
                entry = raw
                if entry.startswith("."):
                    continue
                full = os.path.join(parent, entry)
                suffix = "/" if os.path.isdir(full) else ""
                items.append(f"  {entry}{suffix}")
            listing = "\n" + "\n".join(items[:30])
        except Exception:
            listing = ""
        return f"Error: file not found: {path}{listing}"
    except Exception as exc:
        return f"Error reading file: {exc}"

    offset = int(args.get("offset", 0))
    limit = int(args.get("limit", min(MAX_LINES, len(lines) - offset)))
    selected = lines[offset : offset + limit]
    numbered = "".join(
        f"{offset + i + 1}\t{line}" for i, line in enumerate(selected)
    )

    result = f"File: {path} ({len(lines)} lines)"
    if offset > 0 or limit < len(lines):
        result += f" [showing lines {offset + 1}-{offset + len(selected)}]"
    result += "\n" + numbered

    if offset + limit < len(lines):
        remaining = len(lines) - offset - limit
        result += f"\n... ({remaining} more lines. Use offset={offset + limit} to continue.)"

    return result


read_file_tool = Tool(
    name="read_file",
    description=(
        "Read the contents of a file at the given path. "
        "Optionally specify a line offset and limit to read a portion of the file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file to read"},
            "offset": {"type": "number", "description": "Line number to start from (0-based, default: 0)"},
            "limit": {"type": "number", "description": "Maximum number of lines to read"},
        },
        "required": ["path"],
    },
    execute=execute,
    read_only=True,
)
