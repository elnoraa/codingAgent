from __future__ import annotations

import os
import re
from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

logger = get_logger(__name__)

IGNORE_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".svn",
        ".hg",
        "dist",
        "build",
        ".next",
        "__pycache__",
        ".venv",
    }
)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    raw_pattern = args.get("pattern")
    search_dir = args.get("path") or os.getcwd()
    max_results = int(args.get("maxResults", 100))
    logger.info("execute: pattern=%s, path=%s, maxResults=%d", raw_pattern, search_dir, max_results)
    if not raw_pattern:
        return 'Error: missing required argument "pattern".'

    try:
        regex = re.compile(raw_pattern, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(raw_pattern), re.IGNORECASE)

    results: list[tuple[str, int, str]] = []

    for root, dirs, files in os.walk(search_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

        from src.utils import validate_walk_path

        # Skip directories that are symlinks pointing outside working dir
        root_error = validate_walk_path(root, _ctx.working_directory)
        if root_error:
            dirs.clear()  # Don't recurse into this directory
            continue

        for file in files:
            if file.startswith("."):
                continue
            if len(results) >= max_results:
                break

            path = os.path.join(root, file)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line.rstrip("\n")):
                            results.append((path, i, line.rstrip("\n")[:200]))
                            if len(results) >= max_results:
                                break
            except Exception:
                continue

        if len(results) >= max_results:
            break

    if not results:
        logger.info("No matches found for pattern=%s", raw_pattern)
        return f'No matches found for "{raw_pattern}" in {search_dir}'

    lines: list[str] = []
    for path, num, text in results:
        lines.append(f"{path}\n  {num}:\t{text}")

    logger.info("Found %d matches for pattern=%s", len(results), raw_pattern)
    return f"Found {len(results)} match{'es' if len(results) != 1 else ''}:\n" + "\n".join(lines)


grep_tool = Tool(
    name="grep",
    description=(
        "Search for a pattern in file contents across the project. "
        "Returns matching files and their matching lines with line numbers."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Text or regex pattern to search for"},
            "path": {"type": "string", "description": "Directory to search in (defaults to project root)"},
            "maxResults": {"type": "number", "description": "Maximum results to return (default: 100)"},
        },
        "required": ["pattern"],
    },
    execute=execute,
    read_only=True,
)
