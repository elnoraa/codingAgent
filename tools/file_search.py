from __future__ import annotations

import os
import subprocess
from typing import Any

from tools import Tool, ToolContext

# Type alias for command arguments
CmdArgs: type = list[str]

IGNORE_DIRS = frozenset({
    "node_modules", ".git", ".svn", ".hg", "dist", "build", ".next",
    "__pycache__", ".venv", ".claude", ".mypy_cache", ".pytest_cache",
})


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    pattern = args.get("pattern")
    if not pattern:
        return 'Error: missing required argument "pattern".'

    search_dir = args.get("path") or os.getcwd()
    max_results = int(args.get("maxResults", 100))
    file_pattern = args.get("filePattern") or ""

    # Try ripgrep first (much faster), fall back to grep -r
    rg_cmd = ["rg", "-n", "--no-heading", "--max-count", "20", "-i"]
    if file_pattern:
        rg_cmd.extend(["-g", file_pattern])
    rg_cmd.extend([pattern, search_dir])

    try:
        result = subprocess.run(
            rg_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            return _format_rg_results(result.stdout, pattern, max_results)
        # rg returns 1 when no matches; fall through to grep fallback
    except FileNotFoundError:
        pass  # rg not installed, fall back to grep
    except subprocess.TimeoutExpired:
        return "[Error] rg search timed out, falling back to grep..."

    # Fallback: use grep -r
    grep_cmd: list[str] = ["grep", "-rn", "--include=*", "-i", pattern, search_dir]
    if file_pattern:
        grep_cmd = ["grep", "-rn", "-i", pattern, search_dir]
        # Add --include for each pattern
        include_pats = file_pattern.split(",")
        for pat in include_pats:
            grep_cmd.append("--include")
            grep_cmd.append(pat.strip())

    try:
        result = subprocess.run(
            grep_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if result.returncode > 1:  # grep returns 1 for no matches, >1 for error
            return f"[Error] grep failed: {result.stderr.strip()}"
        if not result.stdout:
            return f'No matches found for "{pattern}" in {search_dir}'
        return _format_grep_results(result.stdout, pattern, max_results)
    except subprocess.TimeoutExpired:
        return "[Error] Search timed out after 60s"
    except Exception as exc:
        return f"[Error] {exc}"


def _format_rg_results(raw: str, pattern: str, max_results: int) -> str:
    lines = raw.strip().split("\n")
    count = min(len(lines), max_results)

    # Group by file
    file_groups: dict[str, list[str]] = {}
    for line in lines[:max_results]:
        if ":" in line:
            filepath, rest = line.split(":", 1)
            file_groups.setdefault(filepath, []).append(rest)

    parts: list[str] = []
    for filepath, matches in file_groups.items():
        parts.append(filepath)
        for m in matches:
            if ":" in m:
                num, text = m.split(":", 1)
                parts.append(f"  {num}:\t{text[:200]}")
            else:
                parts.append(f"  {m[:200]}")

    summary = f'Found {count} match{"es" if count != 1 else ""} for "{pattern}":'
    if len(lines) > max_results:
        summary += f" (showing first {max_results})"

    return summary + "\n" + "\n".join(parts)


def _format_grep_results(raw: str, pattern: str, max_results: int) -> str:
    lines = raw.strip().split("\n")
    count = min(len(lines), max_results)

    parts: list[str] = []
    for line in lines[:max_results]:
        if ":" in line:
            segments = line.split(":", 2)
            if len(segments) == 3:
                filepath, num, text = segments
                parts.append(f"{filepath}\n  {num}:\t{text[:200]}")

    summary = f'Found {count} match{"es" if count != 1 else ""} for "{pattern}":'
    if len(lines) > max_results:
        summary += f" (showing first {max_results})"

    return summary + "\n" + "\n".join(parts)


file_search_tool = Tool(
    name="file_search",
    description=(
        "Search file contents for a text or regex pattern. Uses ripgrep (rg) "
        "if available for much faster results, otherwise falls back to grep. "
        "Returns matching files with line numbers and the matching lines."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Text or regex pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (defaults to current directory)",
            },
            "filePattern": {
                "type": "string",
                "description": 'Optional file glob pattern to filter (e.g. "*.py", "*.{ts,js}")',
            },
            "maxResults": {
                "type": "number",
                "description": "Maximum results to return (default: 100)",
            },
        },
        "required": ["pattern"],
    },
    execute=execute,
    read_only=True,
)
