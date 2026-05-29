from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from src.tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)

IGNORE_DIRS = frozenset({
    "node_modules", ".git", ".svn", ".hg", "dist", "build", ".next",
    "__pycache__", ".venv", ".claude", ".mypy_cache", ".pytest_cache",
})

# File type to icon mapping
FILE_TYPE_MAP: dict[str, str] = {
    ".py": "🐍",
    ".js": "📜",
    ".ts": "📘",
    ".tsx": "⚛️",
    ".jsx": "⚛️",
    ".json": "📋",
    ".md": "📝",
    ".yaml": "⚙️",
    ".yml": "⚙️",
    ".html": "🌐",
    ".css": "🎨",
    ".toml": "⚙️",
    ".ini": "⚙️",
    ".cfg": "⚙️",
    ".gitignore": "🙈",
    ".env": "🔒",
    ".sh": "💻",
    ".bat": "💻",
    ".sql": "🗃️",
    ".svg": "🖼️",
    ".png": "🖼️",
    ".jpg": "🖼️",
    ".jpeg": "🖼️",
    ".gif": "🖼️",
    ".ico": "🖼️",
    ".pdf": "📄",
    ".zip": "📦",
    ".tar": "📦",
    ".gz": "📦",
    ".exe": "⚡",
    ".lock": "🔒",
}

DIR_ICON = "📁"


def _format_size(bytes_size: int) -> str:
    """Format file size in human-readable format."""
    size = float(bytes_size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _get_git_status(path: str, working_dir: str) -> str:
    """Get git status indicator for a file path."""
    try:
        rel_path = os.path.relpath(path, working_dir)
        result = subprocess.run(
            ["git", "status", "--porcelain", rel_path],
            capture_output=True, text=True, cwd=working_dir,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            status_char = result.stdout[0]  # First char: M, A, D, ?, etc.
            indicators = {
                "M": "M", "A": "A", "D": "D", "?": "?", "R": "R",
            }
            return indicators.get(status_char, " ")
        return " "
    except Exception:
        return " "


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    root_dir = args.get("path") or os.getcwd()
    max_depth = min(int(args.get("depth", 3)), 10)
    show_git = bool(args.get("show_git", False))
    show_size = bool(args.get("show_size", False))
    simple = bool(args.get("simple", False))
    logger.info("execute: path=%s, depth=%d", root_dir, max_depth)

    if simple:
        # Original simple format (no icons)
        lines: list[str] = [root_dir + "/"]

        def walk_simple(current: str, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                entries = sorted(os.scandir(current), key=lambda e: (not e.is_dir(), e.name.lower()))
            except PermissionError:
                return
            for entry in entries:
                if entry.name.startswith(".") or entry.name in IGNORE_DIRS:
                    continue

                from src.utils import validate_walk_path
                walk_error = validate_walk_path(entry.path, ctx.working_directory)
                if walk_error:
                    continue

                indent = "  " * depth
                if entry.is_dir():
                    lines.append(f"{indent}{entry.name}/")
                    walk_simple(entry.path, depth + 1)
                else:
                    lines.append(f"{indent}{entry.name}")

        walk_simple(root_dir, 1)
        return "\n".join(lines)

    # Enhanced format with icons
    lines: list[str] = [root_dir + "/"]

    def walk(current: str, depth: int) -> None:
        if depth > max_depth:
            return

        try:
            entries = sorted(os.scandir(current), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            if entry.name.startswith(".") or entry.name in IGNORE_DIRS:
                continue

            from src.utils import validate_walk_path
            walk_error = validate_walk_path(entry.path, ctx.working_directory)
            if walk_error:
                continue

            indent = "  " * depth
            if entry.is_dir():
                lines.append(f"{indent}{DIR_ICON} {entry.name}/")
                walk(entry.path, depth + 1)
            else:
                _, ext = os.path.splitext(entry.name)
                icon = FILE_TYPE_MAP.get(ext, "📄")
                git_status = _get_git_status(entry.path, ctx.working_directory) if show_git else ""
                size_str = f" {_format_size(entry.stat().st_size)}" if show_size else ""
                git_tag = f" [{git_status}]" if git_status and git_status.strip() else ""
                lines.append(f"{indent}{icon} {entry.name}{git_tag}{size_str}")

    walk(root_dir, 1)
    return "\n".join(lines)


directory_tree_tool = Tool(
    name="directory_tree",
    description=(
        "Get a tree view of files and directories. "
        "Shows the structure of a project or directory. "
        "Supports icons, git status (show_git), and file sizes (show_size). "
        "Use simple=true for plain text format."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root directory to show (defaults to project root)"},
            "depth": {"type": "number", "description": "Maximum depth to recurse (default: 3, max: 10)"},
            "show_git": {"type": "boolean", "description": "Show git status indicators (default: false)"},
            "show_size": {"type": "boolean", "description": "Show file sizes (default: false)"},
            "simple": {"type": "boolean", "description": "Use simple format without icons (default: false)"},
        },
    },
    execute=execute,
    read_only=True,
)
