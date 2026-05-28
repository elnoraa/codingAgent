from __future__ import annotations

import logging
import os
import re
from typing import Any

from tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)

IGNORE_DIRS = frozenset({
    "node_modules", ".git", ".svn", ".hg", "dist", "build", ".next",
    "__pycache__", ".venv", ".claude", ".mypy_cache", ".pytest_cache",
})


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    old_text = args.get("oldText")
    new_text = args.get("newText")
    search_dir = args.get("path") or os.getcwd()
    file_pattern = args.get("filePattern") or ""
    max_replacements = int(args.get("maxReplacements", 100))
    confirm_each = bool(args.get("confirm", False))
    logger.info(
        "execute: search_dir=%s, oldText_len=%d, newText_len=%d, filePattern=%s, maxReplacements=%d, confirm=%s",
        search_dir, len(old_text or ""), len(new_text or ""), file_pattern, max_replacements, confirm_each,
    )
    if not old_text:
        return 'Error: missing required argument "oldText".'
    if new_text is None:
        return 'Error: missing required argument "newText".'

    # Build list of files to process
    files_to_search: list[str] = []

    for root, dirs, files in os.walk(search_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

        for file in files:
            if file.startswith("."):
                continue
            if file_pattern:
                if not re.search(file_pattern, file):
                    continue

            path = os.path.join(root, file)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if old_text in content:
                    files_to_search.append(path)
            except Exception:
                continue

            if len(files_to_search) >= max_replacements:
                break

        if len(files_to_search) >= max_replacements:
            break

    if not files_to_search:
        return f'No files found containing "{old_text}" in {search_dir}'

    replaced_count = 0
    skipped_count = 0
    file_details: list[str] = []
    modified_python_files: list[str] = []

    for filepath in files_to_search:
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            file_details.append(f"{filepath}: error reading ({exc})")
            continue

        occurrences = content.count(old_text)
        if confirm_each:
            # Show preview and dry-run
            preview = _get_preview(content, old_text)
            file_details.append(
                f"{filepath}: {occurrences} occurrence(s) [use confirm=false to apply]\n{preview}"
            )
            skipped_count += 1
            continue

        new_content = content.replace(old_text, new_text)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            replaced_count += occurrences
            file_details.append(f"{filepath}: replaced {occurrences} occurrence(s)")
            if filepath.endswith(".py"):
                modified_python_files.append(filepath)
        except Exception as exc:
            file_details.append(f"{filepath}: error writing ({exc})")

    # Summary
    summary = f"Replacements: {replaced_count} applied in {len(files_to_search)} file(s)"
    if skipped_count:
        summary += f", {skipped_count} skipped (confirm mode)"

    result = summary + "\n" + "\n".join(file_details)

    return result


def _get_preview(content: str, old_text: str, context_lines: int = 2) -> str:
    """Show a preview of the file around the first occurrence."""
    lines = content.split("\n")
    first_idx = content.index(old_text)
    line_before = content[:first_idx].count("\n")

    start = max(0, line_before - context_lines)
    end = min(len(lines), line_before + context_lines + 3)

    preview: list[str] = []
    for i in range(start, end):
        marker = ">" if i == line_before else " "
        preview.append(f"{marker} {i + 1}:\t{lines[i]}")

    return "\n".join(preview)


replace_in_files_tool = Tool(
    name="replace_in_files",
    description=(
        "Replace all occurrences of a text string across multiple files. "
        "Can optionally filter by file pattern. Use with caution as this "
        "modifies files in bulk. Set confirm=true to do a dry-run."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "oldText": {
                "type": "string",
                "description": "Exact text to find and replace",
            },
            "newText": {
                "type": "string",
                "description": "Text to replace it with",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (defaults to current directory)",
            },
            "filePattern": {
                "type": "string",
                "description": 'Optional regex pattern to filter filenames (e.g. "\\.py$" for Python files)',
            },
            "maxReplacements": {
                "type": "number",
                "description": "Maximum number of files to modify (default: 100)",
            },
            "confirm": {
                "type": "boolean",
                "description": "If true, only show preview without making changes (default: false)",
            },
        },
        "required": ["oldText", "newText"],
    },
    execute=execute,
)
