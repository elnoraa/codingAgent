from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

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

    # Validate path is within the working directory
    error = ctx.validate_write_path(path)
    if error:
        return error

    # Validate content and path length
    from src.utils import MAX_FILE_CONTENT, MAX_PATH_LENGTH, validate_length

    error = validate_length(content, MAX_FILE_CONTENT, "file content")
    if error:
        return error
    error = validate_length(path, MAX_PATH_LENGTH, "file path")
    if error:
        return error

    # Snapshot existing content before overwriting
    ctx.snapshot_file(path)

    # Check confirm mode — show diff and ask user before applying
    confirm = bool(args.get("confirm", False)) or getattr(ctx, "confirm_edits", False)
    if confirm and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                current = f.read()
            from src.utils import show_diff_and_confirm

            if not show_diff_and_confirm(current, content, path):
                return f"Skipped: {path} (user declined)"
        except OSError:
            pass  # If we can't read the existing file, proceed

    try:
        # Atomic write-path check: validate immediately before writing
        from src.utils import validate_write_path_atomic

        resolved_path = str(Path(path).resolve())
        atomic_error = validate_write_path_atomic(resolved_path, ctx.working_directory)
        if atomic_error:
            return atomic_error

        Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)
        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(content)
        result = f"Successfully wrote {len(content)} bytes to {resolved_path}"
        logger.info("Wrote %d bytes to %s", len(content), resolved_path)
    except Exception as exc:
        logger.error("Error writing file %s: %s", path, exc)
        return f"Error writing file: {exc}"

    # Run post-edit hooks
    from src.tools import run_post_edit_hooks

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
    read_only=False,
)
