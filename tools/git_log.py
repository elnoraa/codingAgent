"""Git log/commit history tool.

Shows recent commit history to help the agent understand project
evolution, see what changed, and when.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    root_dir = args.get("path") or os.getcwd()
    max_count = min(int(args.get("maxCount", 20)), 100)
    branch = args.get("branch", "")

    # Validate path is within the working directory
    error = _ctx.validate_write_path(root_dir)
    if error:
        return error

    # Check if we're in a git repo
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, cwd=root_dir, check=True, timeout=15,
        )
    except subprocess.CalledProcessError:
        return f"[Error] {root_dir} is not inside a git repository"
    except FileNotFoundError:
        return "[Error] git is not installed"

    # Get total commit count
    total = "?"
    try:
        count_result = subprocess.run(
            ["git", "rev-list", "--count", branch or "HEAD"],
            capture_output=True, text=True, cwd=root_dir, timeout=15,
        )
        if count_result.returncode == 0:
            total = count_result.stdout.strip()
    except Exception:
        pass

    # Build the log command with a custom format
    # Format: hash date time author
    #         subject
    log_format = "--format=format:%h  %ai  %an%n%s%n"
    cmd = ["git", "log", f"--max-count={max_count}", log_format]
    if branch:
        cmd.append(branch)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=root_dir, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "[Error] git log timed out after 30s"
    except Exception as exc:
        return f"[Error] {exc}"

    if result.returncode != 0:
        return f"[Error] git log failed: {result.stderr.strip()}"
    if not result.stdout.strip():
        return "No commits found."

    output = f"Commit history (showing {max_count} of {total} total):\n\n"

    # Parse and format the log output
    entries = result.stdout.strip().split("\n\n")
    for entry in entries:
        lines = entry.strip().split("\n")
        if len(lines) >= 2:
            header = lines[0]  # hash date author
            message = lines[1]  # subject
            output += f"  {header}\n  {message}\n\n"
        elif lines:
            output += f"  {lines[0]}\n\n"

    return output.strip()


git_log_tool = Tool(
    name="git_log",
    description=(
        "Show the git commit history for the repository. Displays commit hash, "
        "date, author, and subject line for recent commits. Helps understand "
        "project evolution and context. Optionally filter by branch."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository directory (defaults to current directory)",
            },
            "maxCount": {
                "type": "number",
                "description": "Maximum number of commits to show (default: 20, max: 100)",
            },
            "branch": {
                "type": "string",
                "description": "Branch to show history for (default: current branch)",
            },
        },
    },
    execute=execute,
    read_only=True,
)
