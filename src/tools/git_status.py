from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from src.tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    root_dir = args.get("path") or os.getcwd()
    logger.info("execute: path=%s", root_dir)

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

    # ── Branch name ──────────────────────────────────────────────────────
    try:
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=root_dir,
            check=True,
            timeout=15,
        )
        branch = branch_result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        branch = "(unknown)"

    # ── Status (short) ───────────────────────────────────────────────────
    try:
        status_result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=root_dir,
            check=True,
            timeout=15,
        )
        status_lines = status_result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        status_lines = ""

    # ── Staged vs unstaged counts ───────────────────────────────────────
    staged = 0
    unstaged = 0
    untracked = 0
    if status_lines:
        for line in status_lines.split("\n"):
            line = line.strip()
            if not line:
                continue
            # First two chars: XY (index/worktree)
            # X space = staged, ? space = untracked, space X = unstaged
            if len(line) >= 2:
                x, y = line[0], line[1]
                if x == "?":
                    untracked += 1
                elif x != " ":
                    staged += 1
                elif y != " ":
                    unstaged += 1

    # ── Unpushed commits ────────────────────────────────────────────────
    unpushed_count = 0
    try:
        remote_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "@{upstream}"],
            capture_output=True,
            text=True,
            cwd=root_dir,
            timeout=15,
        )
        if remote_result.returncode == 0:
            upstream = remote_result.stdout.strip()
            log_result = subprocess.run(
                ["git", "log", "--oneline", f"{upstream}..HEAD"],
                capture_output=True,
                text=True,
                cwd=root_dir,
                timeout=15,
            )
            if log_result.stdout.strip():
                unpushed_count = len(log_result.stdout.strip().split("\n"))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass  # No upstream configured

    # ── Build output ────────────────────────────────────────────────────
    parts: list[str] = []
    parts.append(f"On branch {branch}")
    parts.append("")

    if status_lines:
        parts.append(f"Changes ({staged} staged, {unstaged} unstaged, {untracked} untracked):")
        parts.append("")
        for line in status_lines.split("\n"):
            if line.strip():
                # Annotate with color-like markers
                if line.startswith("?"):
                    parts.append(f"  ?? {line[2:].strip()}")
                elif line.startswith(" "):
                    parts.append(f"   → {line[2:].strip()} (unstaged)")
                else:
                    parts.append(f"  {line}")
        parts.append("")
    else:
        parts.append("Working tree clean (nothing to stage/commit).")
        parts.append("")

    if unpushed_count > 0:
        parts.append(f"Unpushed commits: {unpushed_count}")
    else:
        parts.append("Up-to-date with remote (no unpushed commits).")

    return "\n".join(parts)


git_status_tool = Tool(
    name="git_status",
    description=(
        "Show the current git status: branch name, staged/unstaged/untracked file "
        "counts, detailed status, and number of unpushed commits. Read-only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository directory (defaults to current directory)",
            },
        },
    },
    execute=execute,
    read_only=True,
)
