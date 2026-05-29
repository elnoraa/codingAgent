"""Linting integration for the Coding Agent.

Auto-detects configured linters and runs them on modified files.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)

# Linter detection: config files to check
LINTER_CONFIGS: dict[str, dict[str, Any]] = {
    "ruff": {
        "config_files": ["ruff.toml", ".ruff.toml", "pyproject.toml"],
        "check_cmd": ["ruff", "check"],
        "fix_cmd": ["ruff", "check", "--fix"],
    },
    "flake8": {
        "config_files": [".flake8", "setup.cfg", "tox.ini"],
        "check_cmd": ["flake8"],
        "fix_cmd": None,  # flake8 has no auto-fix
    },
    "eslint": {
        "config_files": [".eslintrc.js", ".eslintrc.json", ".eslintrc.yaml",
                         ".eslintrc.yml", "eslint.config.js"],
        "check_cmd": ["npx", "eslint"],
        "fix_cmd": ["npx", "eslint", "--fix"],
    },
}


def detect_linter(working_dir: str) -> str | None:
    """Detect which linter is configured in the project directory.

    Returns the linter name (e.g. 'ruff', 'flake8') or None.
    """
    for name, config in LINTER_CONFIGS.items():
        for cfg_file in config["config_files"]:
            if os.path.exists(os.path.join(working_dir, cfg_file)):
                # For ruff, verify pyproject.toml has [tool.ruff] section
                if cfg_file == "pyproject.toml":
                    try:
                        with open(os.path.join(working_dir, cfg_file)) as f:
                            content = f.read()
                        if "[tool.ruff]" not in content:
                            continue
                    except Exception:
                        continue
                return name
    return None


def run_linter(
    files: list[str],
    working_dir: str,
    fix: bool = False,
) -> str:
    """Run the detected linter on specified files.

    Args:
        files: List of file paths to lint
        working_dir: Working directory (for config detection)
        fix: If True, attempt auto-fix

    Returns:
        Lint output or error message
    """
    from src.utils import green, yellow, red

    linter = detect_linter(working_dir)
    if linter is None:
        return "No linter detected. Supported: ruff, flake8, ESLint"

    config = LINTER_CONFIGS[linter]
    cmd = config["fix_cmd"] if (fix and config["fix_cmd"]) else config["check_cmd"]

    try:
        result = subprocess.run(
            cmd + files,
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=30,
        )

        if result.returncode == 0:
            return f"{green('✓')} {linter}: no issues found"

        # Format output
        output = result.stdout or result.stderr
        if not output:
            return f"{yellow('⚠')} {linter}: issues found (no output details)"

        # Limit output length
        lines = output.strip().split("\n")
        if len(lines) > 30:
            output = "\n".join(lines[:30]) + f"\n... and {len(lines) - 30} more issues"

        return f"{yellow('⚠')} {linter} issues:\n{output}"

    except FileNotFoundError:
        return f"Error: {linter} not installed. Run 'pip install {linter}' first."
    except subprocess.TimeoutExpired:
        return f"Error: {linter} timed out (30s)"
    except Exception as e:
        return f"Error running {linter}: {e}"


# ── Post-edit hook registration ─────────────────────────────────────────


def _lint_post_edit_hook(filepath: str, result: str) -> str:
    """Post-edit hook: run linter on modified file."""
    if filepath.endswith((".py", ".js", ".ts", ".tsx", ".jsx")):
        lint_result = run_linter([filepath], os.getcwd())
        if "no issues found" not in lint_result:
            result += f"\n\n{lint_result}"
    return result


# Register hook when module loads
try:
    from tools import register_post_edit_hook
    register_post_edit_hook(_lint_post_edit_hook)
except ImportError:
    pass
