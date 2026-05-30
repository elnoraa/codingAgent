"""Chat export functionality for the Coding Agent.

Provides Markdown and JSON export of conversation history,
plus full .agent-session export for sharing/archiving.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


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


# ── Full Session Export (Agent Session format) ──────────────────────────


def _format_size(bytes_size: int) -> str:
    """Format file size in human-readable format."""
    size = float(bytes_size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _get_file_listing(directory: str, max_depth: int = 3) -> list[dict[str, Any]]:
    """Get a listing of project files (for context in export)."""
    files: list[dict[str, Any]] = []
    root = Path(directory)

    ignore_dirs = {
        ".git",
        "__pycache__",
        ".venv",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".agent-backups",
    }

    try:
        for path in root.rglob("*"):
            if any(part in ignore_dirs for part in path.parts):
                continue
            if path.is_file():
                rel = path.relative_to(root)
                depth = len(rel.parts)
                if depth <= max_depth:
                    try:
                        files.append(
                            {
                                "path": str(rel),
                                "size": path.stat().st_size,
                                "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                            }
                        )
                    except OSError:
                        pass
    except Exception:
        pass

    return files


def export_full_session(
    output_path: str,
    messages: list[dict[str, object]],
    metadata: dict[str, Any] | None = None,
    snapshots: dict[str, list[tuple[str, str]]] | None = None,
    branches: dict[str, Any] | None = None,
    changelog: list[dict[str, Any]] | None = None,
    tool_stats: dict[str, Any] | None = None,
    working_directory: str = "",
) -> str:
    """Export a full session as a .agent-session JSON file.

    This is a self-contained portable format that includes everything
    needed to resume or review a session.

    Returns the file path on success, or an error message.
    """
    session_data: dict[str, Any] = {
        "version": "1.0",
        "format": "agent-session",
        "exported_at": datetime.now().isoformat(),
        "exported_at_timestamp": time.time(),
    }

    # Add metadata
    if metadata:
        # Remove sensitive data before export
        safe_metadata = {k: v for k, v in metadata.items() if k not in ("api_key", "password", "secret")}
        session_data["metadata"] = safe_metadata
    else:
        session_data["metadata"] = {}

    session_data["metadata"]["working_directory"] = working_directory

    # Add messages (full conversation)
    session_data["messages"] = messages

    # Add snapshots (file state history)
    if snapshots:
        # Convert snapshots to serializable format
        serialized_snapshots: dict[str, list[dict[str, str]]] = {}
        for filepath, snap_list in snapshots.items():
            serialized_snapshots[filepath] = [{"timestamp": ts, "content": content} for ts, content in snap_list]
        session_data["snapshots"] = serialized_snapshots

    # Add branches
    if branches:
        session_data["branches"] = branches

    # Add changelog
    if changelog:
        session_data["changelog"] = changelog

    # Add tool usage statistics
    if tool_stats:
        session_data["tool_stats"] = tool_stats

    # Add file listing (to help understand project state)
    try:
        files = _get_file_listing(working_directory or os.getcwd())
        session_data["files"] = files[:500]  # Limit to 500 files
    except Exception:
        session_data["files"] = []

    # Write to file
    output_path_obj = Path(output_path)
    try:
        output_path_obj.write_text(
            json.dumps(session_data, indent=2, default=str),
            encoding="utf-8",
        )
        size = output_path_obj.stat().st_size
        size_str = _format_size(size)
        logger.info("Session exported to %s (%s)", output_path, size_str)
        return str(output_path_obj)
    except Exception as e:
        logger.error("Failed to export session: %s", e)
        return f"Error: Failed to export session: {e}"


def load_session_file(filepath: str) -> dict[str, Any] | None:
    """Load a previously exported .agent-session file.

    Returns the session data dict, or None if loading fails.
    """
    path = Path(filepath)
    if not path.exists():
        return None
    if path.suffix != ".agent-session":
        logger.warning("Unexpected file extension: %s (expected .agent-session)", path.suffix)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != "agent-session":
            logger.warning("File does not appear to be an agent-session file")
        return data
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to load session file: %s", e)
        return None


def export_summary(data: dict[str, Any]) -> str:
    """Generate a human-readable summary of an exported session."""
    lines: list[str] = []
    lines.append(f"\n{'=' * 60}")
    lines.append("  Session Export Summary")
    lines.append(f"{'=' * 60}")

    meta = data.get("metadata", {})
    lines.append(f"  Exported: {meta.get('exported_at', data.get('exported_at', 'unknown'))}")
    lines.append(f"  Model: {meta.get('model', 'unknown')}")
    lines.append(f"  Mode: {meta.get('mode', 'unknown')}")
    lines.append(f"  Working Dir: {meta.get('working_directory', 'unknown')}")

    messages = data.get("messages", [])
    if messages:
        user_msgs = sum(1 for m in messages if m.get("role") == "user")
        assistant_msgs = sum(1 for m in messages if m.get("role") == "assistant")
        lines.append(f"  Messages: {len(messages)} ({user_msgs} user, {assistant_msgs} assistant)")

    snapshots = data.get("snapshots", {})
    if snapshots:
        lines.append(f"  File Snapshots: {len(snapshots)} file(s)")

    branches = data.get("branches", {})
    if branches:
        branches_info = branches.get("branches", {})
        lines.append(f"  Branches: {len(branches_info)}")

    changelog = data.get("changelog", [])
    if changelog:
        lines.append(f"  Change Log Entries: {len(changelog)}")

    files = data.get("files", [])
    if files:
        lines.append(f"  Project Files: {len(files)}")

    lines.append(f"{'=' * 60}")
    return "\n".join(lines)
