"""Chat export functionality for the Coding Agent.

Provides Markdown and JSON export of conversation history.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, cast


def _safe_filename() -> str:
    """Generate a safe filename like chat-export-20250528-143052."""
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    return f"chat-export-{ts}"


def export_as_markdown(
    messages: list[dict[str, object]],
    mode: str,
    model: str,
    output_dir: str | None = None,
) -> str:
    """Export conversation history as Markdown. Returns the file path."""
    lines: list[str] = [
        "# Chat Export",
        "",
        f"- **Mode**: {mode}",
        f"- **Model**: {model}",
        f"- **Messages**: {len(messages)}",
        f"- **Exported**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
    ]

    for i, msg in enumerate(messages, 1):
        role = cast(str, msg.get("role", "unknown"))
        content = msg.get("content", "")

        role_label = role.upper()
        lines.append(f"## {i}. {role_label}")
        lines.append("")

        if isinstance(content, str):
            lines.append(content)
            lines.append("")
        elif isinstance(content, list):
            blocks = cast("list[dict[str, object]]", content)
            for block in blocks:
                block_type = cast(str, block.get("type", ""))
                if block_type == "text":
                    text = cast(str, block.get("text", ""))
                    lines.append(text)
                    lines.append("")
                elif block_type == "tool_use":
                    tool_name = cast(str, block.get("name", "?"))
                    tool_input = block.get("input", {})
                    lines.append(f"> **Tool: {tool_name}**")
                    input_str = json.dumps(tool_input, indent=2)
                    for input_line in input_str.split("\n"):
                        lines.append(f"> {input_line}")
                    lines.append("")
                elif block_type == "tool_result":
                    result_content = cast(str, block.get("content", ""))
                    if len(result_content) > 500:
                        result_content = result_content[:500] + "\n... [truncated]"
                    lines.append("```")
                    lines.append(result_content)
                    lines.append("```")
                    lines.append("")

        lines.append("---")
        lines.append("")

    # Write to file
    if output_dir is None:
        output_dir = os.getcwd()
    filename = f"{_safe_filename()}.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def export_as_json(
    messages: list[dict[str, object]],
    mode: str,
    model: str,
    output_dir: str | None = None,
) -> str:
    """Export conversation history as JSON. Returns the file path."""
    # Truncate long tool results for readability
    cleaned: list[dict[str, object]] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            blocks = cast("list[dict[str, object]]", content)
            cleaned_blocks: list[dict[str, object]] = []
            for block in blocks:
                b = dict(block)
                block_content = b.get("content", "")
                if isinstance(block_content, str) and len(block_content) > 500:
                    b["content"] = block_content[:500] + "\n... [truncated]"
                cleaned_blocks.append(b)
            msg = dict(msg)
            msg["content"] = cleaned_blocks
        cleaned.append(msg)

    data: dict[str, object] = {
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "model": model,
        "message_count": len(messages),
        "messages": cleaned,
    }

    if output_dir is None:
        output_dir = os.getcwd()
    filename = f"{_safe_filename()}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return filepath
