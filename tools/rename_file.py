from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    source = args.get("source", "")
    destination = args.get("destination", "")
    git_move = bool(args.get("git_move", True))

    if not source:
        return 'Error: missing required argument "source".'
    if not destination:
        return 'Error: missing required argument "destination".'

    # Resolve paths relative to working directory
    src_path = os.path.join(ctx.working_directory, source) if not os.path.isabs(source) else source
    dst_path = os.path.join(ctx.working_directory, destination) if not os.path.isabs(destination) else destination

    if not os.path.exists(src_path):
        return f"Error: source path does not exist: {src_path}"

    if os.path.exists(dst_path):
        return f"Error: destination already exists: {dst_path}"

    # Snapshot both paths for undo support
    ctx.snapshot_file(src_path)
    # If destination exists, snapshot it too (it shouldn't, but safety)
    if os.path.exists(dst_path):
        ctx.snapshot_file(dst_path)

    try:
        if git_move:
            # Try git mv first — works for tracked files, respects git history
            result = subprocess.run(
                ["git", "mv", src_path, dst_path],
                capture_output=True, text=True, cwd=ctx.working_directory,
            )
            if result.returncode == 0:
                logger.info("git mv: %s -> %s", source, destination)
                return f"Moved: {source} -> {destination} (git mv)"
            else:
                # git mv failed — fall through to shutil.move
                logger.info("git mv failed (%s), falling back to shutil.move", result.stderr.strip())

        # Fallback: shutil.move
        shutil.move(src_path, dst_path)
        logger.info("shutil.move: %s -> %s", source, destination)
        return f"Moved: {source} -> {destination}"

    except Exception as exc:
        return f"Error moving {source} -> {destination}: {exc}"


rename_file_tool = Tool(
    name="rename_file",
    description="Rename or move a file or directory. Uses 'git mv' for git-tracked files when git_move is True (default).",
    input_schema={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Source path (relative to working directory or absolute)",
            },
            "destination": {
                "type": "string",
                "description": "Destination path (relative to working directory or absolute)",
            },
            "git_move": {
                "type": "boolean",
                "description": "Use 'git mv' if possible (default: true)",
            },
        },
        "required": ["source", "destination"],
    },
    execute=execute,
    read_only=False,
)
