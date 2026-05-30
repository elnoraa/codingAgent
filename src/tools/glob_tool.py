from __future__ import annotations

import glob as glob_mod
import os
from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    pattern = args.get("pattern")
    search_dir = args.get("path") or os.getcwd()
    logger.info("execute: pattern=%s, path=%s", pattern, search_dir)
    if not pattern:
        return 'Error: missing required argument "pattern".'

    try:
        matches = glob_mod.glob(pattern, root_dir=search_dir, recursive=True)
    except Exception as exc:
        logger.error("Glob search failed: %s", exc)
        return f'Error searching for "{pattern}": {exc}'

    if not matches:
        logger.info("No matches found for pattern=%s", pattern)
        return f'No files found matching "{pattern}" in {search_dir}'

    matches.sort()
    if len(matches) > 200:
        matches = matches[:200]
        matches.append(f"... and {len(matches) - 200} more")

    logger.info("Found %d matches for pattern=%s", len(matches), pattern)
    return f'Found {len(matches)} result{"s" if len(matches) != 1 else ""} for "{pattern}":\n' + "\n".join(matches)


glob_tool = Tool(
    name="glob",
    description=(
        "Search for files and directories matching a glob pattern. "
        "Supports ** (any depth), * (filename), ? (single char) patterns."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": 'Glob pattern (e.g. "**/*.py", "src/**/*.css")',
            },
            "path": {
                "type": "string",
                "description": "Directory to search from (defaults to project root)",
            },
        },
        "required": ["pattern"],
    },
    execute=execute,
    read_only=True,
)
