from __future__ import annotations

import os
import subprocess
from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    root_dir = args.get("path") or os.getcwd()
    staged = bool(args.get("staged", False))
    max_lines = int(args.get("maxLines", 200))
    logger.info("execute: path=%s, staged=%s, maxLines=%d", root_dir, staged, max_lines)

    # Validate path is within the working directory
    error = _ctx.validate_write_path(root_dir)
    if error:
        return error

    # Check if we're in a git repo
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            cwd=root_dir,
            check=True,
        )
    except subprocess.CalledProcessError:
        return f"[Error] {root_dir} is not inside a git repository"
    except FileNotFoundError:
        return "[Error] git is not installed"

    # Build the diff command
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=root_dir,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "[Error] git diff timed out after 30s"
    except Exception as exc:
        return f"[Error] {exc}"

    output = result.stdout
    if not output:
        return "No changes detected (working tree is clean)."

    # Truncate if too long
    lines = output.split("\n")
    if len(lines) > max_lines:
        output = "\n".join(lines[:max_lines])
        output += f"\n... ({len(lines) - max_lines} more lines. Use a more specific path or increase maxLines.)"

    return output


diff_tool = Tool(
    name="diff",
    description=(
        "Show the git diff of uncommitted changes in the working directory. "
        "Useful for reviewing what has changed before committing, or for "
        "understanding the current state of the project."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository directory (defaults to current directory)",
            },
            "staged": {
                "type": "boolean",
                "description": "Show only staged changes (default: false, shows unstaged changes)",
            },
            "maxLines": {
                "type": "number",
                "description": "Maximum number of diff lines to return (default: 200)",
            },
        },
    },
    execute=execute,
    read_only=True,
)
