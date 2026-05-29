"""File content verification tool.

Confirms that specific text patterns exist or are absent in a file.
Returns structured pass/fail results per pattern. Helps the agent confirm
edits were applied correctly without reading the entire file.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from src.tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    path = str(args.get("path", ""))
    raw_should_contain: list[str] = list(args.get("shouldContain", []) or [])
    raw_should_not_contain: list[str] = list(args.get("shouldNotContain", []) or [])
    use_regex = bool(args.get("regex", False))

    if not path:
        return 'Error: missing required argument "path".'
    if not raw_should_contain and not raw_should_not_contain:
        return "Error: provide at least one of 'shouldContain' or 'shouldNotContain'."

    if not os.path.isfile(path):
        return f"Error: file not found: {path}"

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        return f"Error reading file: {exc}"

    results: list[str] = []
    all_passed = True

    for pattern in raw_should_contain:
        if use_regex:
            found = bool(re.search(pattern, content))
        else:
            found = pattern in content
        if found:
            results.append(f"  PASS  Contains: {_preview_pattern(pattern)}")
        else:
            results.append(f"  FAIL  Missing:  {_preview_pattern(pattern)}")
            all_passed = False

    for pattern in raw_should_not_contain:
        if use_regex:
            found = bool(re.search(pattern, content))
        else:
            found = pattern in content
        if not found:
            results.append(f"  PASS  Absent:   {_preview_pattern(pattern)}")
        else:
            results.append(f"  FAIL  Present:  {_preview_pattern(pattern)}")
            all_passed = False

    rel_path = os.path.relpath(path, ctx.working_directory) if ctx.working_directory else path
    header = f"Verification of {rel_path}:"
    status = "\nALL CHECKS PASSED" if all_passed else "\nSOME CHECKS FAILED"
    return header + "\n" + "\n".join(results) + status


def _preview_pattern(pattern: str, max_len: int = 60) -> str:
    """Show a truncated preview of the pattern."""
    if len(pattern) <= max_len:
        return repr(pattern)
    return repr(pattern[:max_len] + "...")


verify_content_tool = Tool(
    name="verify_content",
    description=(
        "Verify that a file contains (or does not contain) specific text patterns. "
        "Returns a structured pass/fail result for each pattern. "
        "Useful for confirming edits were applied correctly without reading the entire file. "
        "Supports both plain text and regex matching via the 'regex' flag."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to verify",
            },
            "shouldContain": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of text patterns that should all be present in the file",
            },
            "shouldNotContain": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of text patterns that should all be absent from the file",
            },
            "regex": {
                "type": "boolean",
                "description": "If true, treat patterns as regex instead of plain text (default: false)",
            },
        },
        "required": ["path"],
    },
    execute=execute,
    read_only=True,
)
