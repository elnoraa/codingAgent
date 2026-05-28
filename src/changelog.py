"""Change log / audit trail for session file modifications.

Tracks every file modification within a session with timestamp,
tool used, and summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ChangeEntry:
    """A single file modification entry in the audit trail."""

    timestamp: str
    tool: str
    path: str
    summary: str = ""
    args: dict[str, Any] = field(default_factory=dict)


def format_changelog(entries: list[ChangeEntry], max_entries: int = 50) -> str:
    """Format changelog entries as a human-readable string."""
    if not entries:
        return "  No changes recorded yet."

    lines: list[str] = []
    for entry in entries[-max_entries:]:
        ts = entry.timestamp
        if len(ts) > 19:
            ts = ts[:19]  # truncate ISO timestamp
        lines.append(f"  {ts}  {entry.tool:<16} {entry.path}")
        if entry.summary:
            lines.append(f"  {' ' * 20} {entry.summary[:80]}")
    return "\n".join(lines)
