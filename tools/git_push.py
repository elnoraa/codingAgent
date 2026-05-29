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
    branch = args.get("branch") or ""
    remote = args.get("remote") or "origin"
    logger.info("execute: path=%s, branch=%s, remote=%s", root_dir, branch, remote)

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

    # Auto-detect current branch if not specified
    if not branch:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=root_dir,
                check=True,
                timeout=15,
            )
            branch = result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return f"[Error] Could not determine current branch: {exc}"

    # Check if there are any commits (branches with no commits can't push)
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
            cwd=root_dir,
            timeout=15,
        )
        if result.returncode != 0:
            return "[Error] No commits to push. Make a commit first."
    except subprocess.TimeoutExpired:
        return "[Error] git log timed out"

    # Check for unpushed commits
    try:
        unpushed = subprocess.run(
            ["git", "log", f"@{{{remote}}}" if remote else "@{upstream}", "..", "--oneline"],
            capture_output=True,
            text=True,
            cwd=root_dir,
            timeout=15,
        )
        unpushed_count = len(unpushed.stdout.strip().split("\n")) if unpushed.stdout.strip() else 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        unpushed_count = 0  # Might not have upstream set yet

    # Push to remote
    try:
        result = subprocess.run(
            ["git", "push", remote, branch],
            capture_output=True,
            text=True,
            cwd=root_dir,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return f"[Error] git push timed out (>{60}s). The remote may be slow or unreachable."
    except Exception as exc:
        return f"[Error] {exc}"

    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Provide helpful messages for common errors
        if "no upstream branch" in stderr.lower():
            suggestion = f"\n  Hint: Set upstream with: git push --set-upstream {remote} {branch}"
            return f"[Error] Push failed — no upstream branch configured.{suggestion}\n\n{stderr}"
        elif "failed to push" in stderr.lower():
            # Could be rejected (diverged), network error, etc.
            return f"[Error] Push to {remote}/{branch} failed:\n{stderr}"
        return f"[Error] git push failed:\n{stderr}"

    output = result.stdout.strip() or result.stderr.strip()
    if output:
        return f"✅ Pushed to {remote}/{branch}\n{output}"
    else:
        return f"✅ Successfully pushed to {remote}/{branch} (everything up-to-date)"


git_push_tool = Tool(
    name="git_push",
    description=(
        "Push commits from the current (or specified) branch to a remote repository. "
        "Auto-detects the current branch if not specified. Shows what was pushed."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "branch": {
                "type": "string",
                "description": "Branch to push (defaults to the current branch)",
            },
            "remote": {
                "type": "string",
                "description": "Remote name to push to (default: origin)",
            },
            "path": {
                "type": "string",
                "description": "Repository directory (defaults to current directory)",
            },
        },
    },
    execute=execute,
    read_only=False,
)
