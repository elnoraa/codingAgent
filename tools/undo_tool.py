"""Undo/Rollback tool — list and revert file snapshots.

Snapshots are taken by write_file and edit_file before modifying files.
This tool allows the LLM (or user via /rollback) to list and revert changes.
"""

from __future__ import annotations

import os
import time
from typing import Any

from tools import Tool, ToolContext

undo_tool = Tool(
    name="undo",
    description=(
        "List file snapshots or revert a file to a previous snapshot. "
        "Snapshots are automatically taken before write_file or edit_file modifications. "
        'Use with action="list" to show all snapshots, or action="revert" with path and optional index to restore.'
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": '"list" to show snapshots, "revert" to restore a file',
                "enum": ["list", "revert"],
            },
            "path": {
                "type": "string",
                "description": "File path to revert (required for revert action)",
            },
            "index": {
                "type": "number",
                "description": "Snapshot index to restore (-1 = last/previous, default: -1)",
            },
        },
        "required": ["action"],
    },
    execute=lambda args, ctx: _execute(args, ctx),
    read_only=False,
)


def _execute(args: dict[str, Any], ctx: ToolContext) -> str:
    action = args.get("action", "")
    if action not in ("list", "revert"):
        return 'Error: action must be "list" or "revert".'

    if action == "list":
        return _list_snapshots(ctx)

    path = args.get("path", "")
    if not path:
        return 'Error: path is required for revert action.'

    if ctx.file_snapshots is None:
        return "Error: snapshots not available (no modifications made this session)."

    index = int(args.get("index", -1))
    success = ctx.revert_to_snapshot(path, index)
    if success:
        rel_path = os.path.relpath(path, ctx.working_directory) if ctx.working_directory else path
        return f"Reverted {rel_path} to snapshot at index {index}."
    snapshots = ctx.get_snapshots(path)
    if not snapshots.get(path):
        return f"No snapshots found for: {path}"
    return f"Failed to revert {path}. Invalid index {index} (have {len(snapshots[path])} snapshots)."


def _list_snapshots(ctx: ToolContext) -> str:
    if ctx.file_snapshots is None or not ctx.file_snapshots:
        return "No snapshots recorded. Snapshots are taken automatically when write_file or edit_file is called."

    lines: list[str] = ["File Snapshots:"]
    for filepath, snapshots in sorted(ctx.file_snapshots.items()):
        rel_path = os.path.relpath(filepath, ctx.working_directory) if ctx.working_directory else filepath
        lines.append(f"  {rel_path}")
        for i, (ts, _content) in enumerate(snapshots):
            time_str = time.strftime("%H:%M:%S", time.localtime(float(ts)))
            preview = _content[:60].replace("\n", " ") if _content else "(empty/new file)"
            lines.append(f"    [{i}] {time_str} — {preview}...")
    return "\n".join(lines)
