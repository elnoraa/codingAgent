"""Python syntax checking tool.

Uses Python's built-in py_compile module to validate .py files
for syntax errors without executing them. Fast, safe, and returns
line-level error details.
"""

from __future__ import annotations

import logging
import os
import py_compile
from typing import Any

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)

IGNORE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache",
})


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    path = args.get("path", "")
    if not path:
        return 'Error: missing required argument "path".'

    if not os.path.exists(path):
        return f"Error: path not found: {path}"

    files_to_check: list[str] = []
    if os.path.isfile(path):
        if path.endswith(".py"):
            files_to_check.append(path)
        else:
            return f"Error: {path} is not a Python (.py) file."
    elif os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

            from src.utils import validate_walk_path
            root_error = validate_walk_path(root, _ctx.working_directory)
            if root_error:
                dirs.clear()
                continue

            for f in files:
                if f.endswith(".py"):
                    files_to_check.append(os.path.join(root, f))
    else:
        return f"Error: {path} is not a file or directory."

    if not files_to_check:
        return "No Python files found to check."

    results: list[str] = []
    errors = 0
    for filepath in sorted(files_to_check):
        try:
            py_compile.compile(filepath, doraise=True)
            results.append(f"OK  {filepath}")
        except py_compile.PyCompileError as exc:
            errors += 1
            msg = str(exc)
            results.append(f"ERR {filepath}  {msg}")

    summary = f"\n{'─' * 40}\nChecked {len(files_to_check)} file(s): {len(files_to_check) - errors} passed, {errors} failed."
    return "\n".join(results) + summary


syntax_check_tool = Tool(
    name="syntax_check",
    description=(
        "Check one or more Python files for syntax errors using Python's built-in "
        "compiler. Fast and safe — does NOT execute any code, only parses it. "
        "Can check a single file or an entire directory recursively. "
        "Returns line-level error details for any invalid files."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to a .py file or directory of Python files to check",
            },
        },
        "required": ["path"],
    },
    execute=execute,
    read_only=True,
)
