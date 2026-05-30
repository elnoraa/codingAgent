"""Pre-commit hook management for the Coding Agent."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

logger = get_logger(__name__)

PRE_COMMIT_CONFIG = ".pre-commit-config.yaml"


def _run_precommit(cmd: list[str], ctx: ToolContext, timeout: int = 60) -> tuple[int, str, str]:
    """Run a pre-commit command."""
    try:
        result = subprocess.run(
            ["pre-commit"] + cmd,
            capture_output=True,
            text=True,
            cwd=ctx.working_directory,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "Error: pre-commit not found. Install with: pip install pre-commit"
    except subprocess.TimeoutExpired:
        return -1, "", f"Error: pre-commit timed out ({timeout}s)"
    except Exception as e:
        return -1, "", f"Error: {e}"


def _load_config(ctx: ToolContext) -> dict[str, Any] | None:
    """Load the pre-commit config file."""
    config_path = os.path.join(ctx.working_directory, PRE_COMMIT_CONFIG)
    if not os.path.exists(config_path):
        return None
    try:
        import yaml

        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.debug("Failed to load %s: %s", PRE_COMMIT_CONFIG, e)
        return None


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    action = args.get("action", "status").lower()
    logger.info("execute: action=%s", action)

    if action == "status" or action == "check":
        # Check if config exists and hooks are installed
        config = _load_config(ctx)
        if config is None:
            logger.info("No pre-commit config found in %s", ctx.working_directory)
            return "No .pre-commit-config.yaml found in the working directory."

        repos = config.get("repos", [])
        hook_count = sum(len(r.get("hooks", [])) for r in repos)

        installed = os.path.exists(os.path.join(ctx.working_directory, ".git", "hooks", "pre-commit"))

        result = [
            "\n  Pre-commit Configuration:",
            f"  {'─' * 40}",
            f"  Config: {os.path.join(ctx.working_directory, PRE_COMMIT_CONFIG)}",
            f"  Hooks installed: {'Yes' if installed else 'No'}",
            f"  Repos configured: {len(repos)}",
            f"  Total hooks: {hook_count}",
        ]

        # List hooks
        for repo in repos:
            repo_url = repo.get("repo", "")
            rev = repo.get("rev", "")
            hooks = repo.get("hooks", [])
            hook_names = [h.get("id", "?") for h in hooks]
            result.append(f"  \n  {repo_url} ({rev})")
            for hook_name in hook_names:
                result.append(f"    └ {hook_name}")

        return "\n".join(result)

    elif action == "install":
        # Install git hooks
        ret, stdout, stderr = _run_precommit(["install"], ctx)
        if ret != 0:
            return f"Install failed:\n{stderr}"
        return f"Pre-commit hooks installed.\n{stdout}"

    elif action == "run":
        # Run hooks on all files or specific files
        files = args.get("files", "")
        all_files = args.get("all_files", True)
        hook_id = args.get("hook", "")

        cmd = ["run"]
        if hook_id:
            cmd.append(hook_id)
        if all_files:
            cmd.append("--all-files")
        if files:
            cmd.extend(["--files"] + files.split())

        ret, stdout, stderr = _run_precommit(cmd, ctx, timeout=120)

        if ret == 0:
            return f"All hooks passed.\n{stdout[:2000]}"
        else:
            return f"Hooks failed (exit {ret}):\n{stdout or stderr}"

    elif action == "update" or action == "autoupdate":
        # Auto-update hook versions
        ret, stdout, stderr = _run_precommit(["autoupdate"], ctx, timeout=120)
        if ret != 0:
            return f"Auto-update failed:\n{stderr}"
        return f"Hooks updated:\n{stdout[:2000]}"

    elif action == "validate" or action == "check-config":
        # Validate the config file
        ret, stdout, stderr = _run_precommit(["validate-config"], ctx)
        if ret != 0:
            return f"Config validation failed:\n{stderr}"
        return "Config is valid."

    elif action == "clean":
        # Clean cached hooks
        ret, stdout, stderr = _run_precommit(["clean"], ctx)
        if ret != 0:
            return f"Clean failed:\n{stderr}"
        return f"Cache cleaned.\n{stdout}"

    else:
        return f"Unknown action: {action}\nAvailable actions: status, install, run, update, validate, clean"


precommit_tool = Tool(
    name="precommit",
    description=(
        "Manage pre-commit hooks. Actions: status (show config and hook status), "
        "install (install git hooks), run (run hooks on files), "
        "update (auto-update hook versions), validate (check config), "
        "clean (clean cached hooks)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": ["status", "install", "run", "update", "validate", "clean"],
            },
            "files": {
                "type": "string",
                "description": "Specific files to run hooks on (space-separated, for run action)",
            },
            "all_files": {
                "type": "boolean",
                "description": "Run on all files (for run action, default: true)",
            },
            "hook": {
                "type": "string",
                "description": "Specific hook ID to run (for run action)",
            },
        },
        "required": ["action"],
    },
    execute=execute,
    read_only=False,
)
