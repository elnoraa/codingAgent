"""Git branch management tool."""

from __future__ import annotations

import subprocess
from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def _run_git(cmd: list[str], ctx: ToolContext) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + cmd,
            capture_output=True,
            text=True,
            cwd=ctx.working_directory,
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
    action = args.get("action", "list").lower()

    if action == "list":
        ret, stdout, stderr = _run_git(["branch"], ctx)
        if ret != 0:
            return f"Error listing branches:\n{stderr}"
        return stdout or "(no branches)"

    elif action == "create":
        name = args.get("name", "")
        if not name:
            return 'Error: missing required argument "name" for create action.'
        ret, stdout, stderr = _run_git(["branch", name], ctx)
        if ret != 0:
            return f"Error creating branch '{name}':\n{stderr}"
        return f"Created branch: {name}"

    elif action == "switch":
        name = args.get("name", "")
        if not name:
            return 'Error: missing required argument "name" for switch action.'
        ret, stdout, stderr = _run_git(["checkout", name], ctx)
        if ret != 0:
            return f"Error switching to branch '{name}':\n{stderr}"
        return f"Switched to branch: {name}"

    elif action == "merge":
        source = args.get("source", "")
        if not source:
            return 'Error: missing required argument "source" for merge action.'
        ret, stdout, stderr = _run_git(["merge", source], ctx)
        if ret != 0:
            return f"Error merging '{source}':\n{stderr}"
        return f"Merged '{source}' into current branch.\n{stdout}"

    elif action == "delete":
        name = args.get("name", "")
        if not name:
            return 'Error: missing required argument "name" for delete action.'
        ret, stdout, stderr = _run_git(["branch", "-d", name], ctx)
        if ret != 0:
            return f"Error deleting branch '{name}':\n{stderr}"
        return f"Deleted branch: {name}"

    elif action == "force_delete":
        name = args.get("name", "")
        if not name:
            return 'Error: missing required argument "name" for force_delete action.'
        if not args.get("confirm"):
            return "Error: force_delete requires confirm=True. Use `delete` for safe deletion."
        ret, stdout, stderr = _run_git(["branch", "-D", name], ctx)
        if ret != 0:
            return f"Error force-deleting branch '{name}':\n{stderr}"
        return f"Force-deleted branch: {name}"

    elif action == "diff":
        branch1 = args.get("branch1", "")
        branch2 = args.get("branch2", "")
        if not branch1 or not branch2:
            return 'Error: missing required arguments "branch1" and "branch2" for diff action.'
        ret, stdout, stderr = _run_git(["diff", branch1, branch2], ctx)
        if ret != 0:
            return f"Error diffing branches:\n{stderr}"
        return stdout or "(no differences)"

    else:
        return f"Unknown action: {action}\nAvailable actions: list, create, switch, merge, delete, force_delete, diff"


git_branch_tool = Tool(
    name="git_branch",
    description="Manage git branches. Actions: list, create, switch, merge, delete, force_delete, diff.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": ["list", "create", "switch", "merge", "delete", "force_delete", "diff"],
            },
            "name": {
                "type": "string",
                "description": "Branch name (for create, switch, delete, force_delete)",
            },
            "source": {
                "type": "string",
                "description": "Source branch to merge (for merge action)",
            },
            "branch1": {
                "type": "string",
                "description": "First branch for diff",
            },
            "branch2": {
                "type": "string",
                "description": "Second branch for diff",
            },
            "confirm": {
                "type": "boolean",
                "description": "Must be true for destructive actions (force_delete)",
            },
        },
        "required": ["action"],
    },
    execute=execute,
    read_only=False,
)
