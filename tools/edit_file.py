from __future__ import annotations

import logging
from typing import Any

from tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    path = args.get("path")
    old_text = args.get("oldText") or args.get("old_string")
    new_text = args.get("newText") or args.get("new_string")
    logger.info("execute: path=%s, oldText_len=%d, newText_len=%d", path, len(old_text or ""), len(new_text or ""))
    if not path:
        return 'Error: missing required argument "path".'
    if not old_text:
        return 'Error: missing required argument "oldText" (or "old_string").'
    if new_text is None:
        return 'Error: missing required argument "newText" (or "new_string").'

    # Snapshot existing content before editing
    ctx.snapshot_file(path)

    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:
        return f"Error reading file: {exc}"

    occurrences = content.count(old_text)

    if occurrences == 0:
        lines = content.split("\n")
        if len(lines) > 20:
            preview = "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(lines[:10]))
            preview += f"\n... (file has {len(lines)} lines)"
        else:
            preview = content
        return (
            f"Error: Could not find the exact text to replace.\n\n"
            f"Current file content:\n{preview}"
        )

    if occurrences > 1:
        return (
            f"Error: Found {occurrences} occurrences of the text. "
            "Please include more surrounding context to make the match unique."
        )

    new_content = content.replace(old_text, new_text)

    # Check confirm mode — show diff and ask user before applying
    confirm = bool(args.get("confirm", False)) or getattr(ctx, 'confirm_edits', False)
    if confirm:
        from src.utils import show_diff_and_confirm
        if not show_diff_and_confirm(content, new_content, path):
            return f"Skipped: {path} (user declined)"

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as exc:
        return f"Error writing file: {exc}"

    old_preview = old_text if len(old_text) <= 80 else old_text[:80] + "..."
    result = f'Applied edit to {path}. Replaced:\n"""\n{old_preview}\n"""'
    logger.info("Edit applied to %s: replaced %d chars with %d chars", path, len(old_text), len(new_text))

    # Run post-edit hooks
    from tools import run_post_edit_hooks
    result = run_post_edit_hooks(path, result)

    return result


edit_file_tool = Tool(
    name="edit_file",
    description=(
        "Make targeted edits to a file by finding an exact block of text "
        "and replacing it with new content. The oldText (or old_string) must match exactly, "
        "including whitespace. If the text is found more than once, the edit "
        "is rejected to avoid ambiguity."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file to edit"},
            "oldText": {
                "type": "string",
                "description": "Exact text to search for (must match exactly, including whitespace). Also accepts 'old_string' as an alias.",
            },
            "newText": {"type": "string", "description": "Text to replace it with. Also accepts 'new_string' as an alias."},
        },
        "required": ["path", "oldText", "newText"],
    },
    execute=execute,
)
