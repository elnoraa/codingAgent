"""Git undo/revert tool for safe repository operations."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from src.tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)


def _run_git(cmd: list[str], ctx: ToolContext) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + cmd,
            capture_output=True, text=True, cwd=ctx.working_directory,
            timeout=30,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Error: git command timed out"
    except FileNotFoundError:
        return -1, "", "Error: git not found"
    except Exception as e:
        return -1, "", f"Error: {e}"


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    action = args.get("action", "").lower()

    if not action:
        return (
            "Error: missing required argument 'action'.\n"
            "Available actions: unstage, undo_commit, reset_soft, reset_hard, discard"
        )

    if action == "unstage":
        files = args.get("files", "")
        cmd = ["reset", "HEAD"]
        if files:
            cmd.extend(files.split())
        ret, stdout, stderr = _run_git(cmd, ctx)
        if ret != 0:
            return f"Error unstage:\n{stderr}"
        return "Unstaged changes." + (f"\n{stdout}" if stdout else "")

    elif action == "undo_commit":
        commit = args.get("commit", "")
        if not commit:
            return 'Error: missing required argument "commit" for undo_commit action.'
        ret, stdout, stderr = _run_git(["revert", commit], ctx)
        if ret != 0:
            return f"Error reverting commit '{commit}':\n{stderr}"
        return f"Reverted commit: {commit}\n{stdout}"

    elif action == "reset_soft":
        ret, stdout, stderr = _run_git(["reset", "--soft", "HEAD~1"], ctx)
        if ret != 0:
            return f"Error soft reset:\n{stderr}"
        return "Soft reset completed (HEAD~1, changes staged)."

    elif action == "reset_hard":
        ref = args.get("ref", "HEAD")
        if not args.get("confirm"):
            # Show preview of changes that will be discarded
            ret, stdout, stderr = _run_git(["diff", "--stat"], ctx)
            preview = f"\n{stdout}" if stdout else " (no uncommitted changes)"
            return (
                f"Error: reset_hard requires confirm=True.\n"
                f"Changes that will be discarded:{preview}\n"
                f"Pass confirm=True to proceed."
            )
        ret, stdout, stderr = _run_git(["reset", "--hard", ref], ctx)
        if ret != 0:
            return f"Error reset --hard {ref}:\n{stderr}"
        return f"Hard reset to {ref} completed.\n{stdout}"

    elif action == "discard":
        files = args.get("files", "")
        if not files:
            return 'Error: missing required argument "files" for discard action.'
        if not args.get("confirm"):
            # Show preview
            ret, stdout, stderr = _run_git(["diff", "--stat"] + files.split(), ctx)
            preview = f"\n{stdout}" if stdout else " (no changes to discard)"
            return (
                f"Error: discard requires confirm=True.\n"
                f"Changes that will be discarded:{preview}\n"
                f"Pass confirm=True to proceed."
            )
        ret, stdout, stderr = _run_git(["checkout", "--"] + files.split(), ctx)
        if ret != 0:
            return f"Error discarding changes:\n{stderr}"
        return f"Discarded changes in: {files}\n{stdout}"

    else:
        return (
            f"Unknown action: {action}\n"
            f"Available actions: unstage, undo_commit, reset_soft, reset_hard, discard"
        )


git_revert_tool = Tool(
    name="git_revert",
    description=(
        "Undo/revert git changes. Actions: unstage (reset HEAD), "
        "undo_commit (git revert), reset_soft (--soft HEAD~1), "
        "reset_hard (--hard <ref>, requires confirm=True), "
        "discard (checkout -- <files>, requires confirm=True)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": ["unstage", "undo_commit", "reset_soft", "reset_hard", "discard"],
            },
            "files": {
                "type": "string",
                "description": "Files to unstage or discard (space-separated)",
            },
            "commit": {
                "type": "string",
                "description": "Commit hash to revert (for undo_commit)",
            },
            "ref": {
                "type": "string",
                "description": "Reference for reset_hard (default: HEAD)",
            },
            "confirm": {
                "type": "boolean",
                "description": "Must be true for destructive actions (reset_hard, discard)",
            },
        },
        "required": ["action"],
    },
    execute=execute,
    read_only=False,
)
