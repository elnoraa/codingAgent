from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    path = args.get("path")
    content = args.get("content")
    content_len = len(content) if isinstance(content, str) else 0
    logger.info("execute: path=%s, content_len=%d", path, content_len)
    if not path:
        return 'Error: missing required argument "path".'
    if content is None:
        return 'Error: missing required argument "content".'

    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        result = f"Successfully wrote {len(content)} bytes to {path}"
        logger.info("Wrote %d bytes to %s", len(content), path)
    except Exception as exc:
        logger.error("Error writing file %s: %s", path, exc)
        return f"Error writing file: {exc}"

    return result


write_file_tool = Tool(
    name="write_file",
    description=(
        "Write content to a file. Creates the file and any parent directories "
        "if they do not exist. Overwrites existing content."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file to write"},
            "content": {"type": "string", "description": "Content to write to the file"},
        },
        "required": ["path", "content"],
    },
    execute=execute,
)
