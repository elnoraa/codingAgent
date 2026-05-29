from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    path = args.get("path")
    content = args.get("content")
    content_len = len(content) if isinstance(content, str) else 0
    logger.info("execute: path=%s, content_len=%d", path, content_len)
    if not path:
        return 'Error: missing required argument "path".'
    if content is None:
        return 'Error: missing required argument "content".'

    # Snapshot existing content before overwriting
    ctx.snapshot_file(path)

    # Check confirm mode — show diff and ask user before applying
    confirm = bool(args.get("confirm", False)) or getattr(ctx, 'confirm_edits', False)
    if confirm and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = f.read()
            from src.utils import show_diff_and_confirm
            if not show_diff_and_confirm(current, content, path):
                return f"Skipped: {path} (user declined)"
        except (OSError, IOError):
            pass  # If we can't read the existing file, proceed

    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        result = f"Successfully wrote {len(content)} bytes to {path}"
        logger.info("Wrote %d bytes to %s", len(content), path)
    except Exception as exc:
        logger.error("Error writing file %s: %s", path, exc)
        return f"Error writing file: {exc}"

    # Run post-edit hooks
    from tools import run_post_edit_hooks
    result = run_post_edit_hooks(path, result)

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
