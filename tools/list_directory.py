from __future__ import annotations

import logging
import os
from typing import Any

from tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)

IGNORE_DIRS = frozenset({
    "node_modules", ".git", ".svn", ".hg", "dist", "build", ".next",
    "__pycache__", ".venv", ".claude", ".mypy_cache", ".pytest_cache",
})


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    root_dir = args.get("path") or os.getcwd()
    show_hidden = bool(args.get("showHidden", False))
    max_items = int(args.get("maxItems", 100))
    logger.info("execute: path=%s, showHidden=%s, maxItems=%d", root_dir, show_hidden, max_items)

    try:
        entries = sorted(os.scandir(root_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return f"Error: permission denied reading {root_dir}"
    except FileNotFoundError:
        return f"Error: directory not found {root_dir}"
    except Exception as exc:
        return f"Error: {exc}"

    dirs: list[str] = []
    files: list[str] = []

    for entry in entries:
        if not show_hidden and entry.name.startswith("."):
            continue
        if entry.name in IGNORE_DIRS:
            continue
        if entry.is_dir():
            dirs.append(entry.name + "/")
        else:
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            files.append(f"{entry.name} ({_format_size(size)})")

    results = dirs + files
    total = len(results)

    if total > max_items:
        results = results[:max_items]
        results.append(f"... and {total - max_items} more")

    header = f"Directory: {root_dir} ({total} items)"
    if results:
        return header + "\n" + "\n".join(results)
    return header + " (empty)"


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024**2:
        return f"{size / 1024:.1f}K"
    elif size < 1024**3:
        return f"{size / 1024**2:.1f}M"
    return f"{size / 1024**3:.1f}G"


list_directory_tool = Tool(
    name="list_directory",
    description=(
        "List the contents of a directory. Shows directories first, then files "
        "with their sizes. Useful for exploring a project structure."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (defaults to current working directory)",
            },
            "showHidden": {
                "type": "boolean",
                "description": "Whether to show hidden files (dotfiles, default: false)",
            },
            "maxItems": {
                "type": "number",
                "description": "Maximum number of items to show (default: 100)",
            },
        },
    },
    execute=execute,
    read_only=True,
)
