"""Core data types for the Coding Agent tool system.

This module defines the fundamental types used across the entire tool
ecosystem: ``Tool``, ``ToolContext``, ``ToolRegistry``, plus helpers
for post-edit hooks and session file-tamper detection.

These types were extracted from ``src/tools/__init__.py`` to keep the
tool package focused on module discovery and reloading.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import types

_logger = logging.getLogger(__name__)


# ── Post-edit hook registry ──────────────────────────────────────────────────

_post_edit_hooks: list[Callable[[str, str], str]] = []


def register_post_edit_hook(hook: Callable[[str, str], str]) -> None:
    """Register a hook that runs after file edits.

    Hook signature: (filepath, result_message) -> updated_result_message
    """
    _post_edit_hooks.append(hook)


def run_post_edit_hooks(filepath: str, result: str) -> str:
    """Run all registered post-edit hooks and return updated result."""
    for hook in _post_edit_hooks:
        try:
            result = hook(filepath, result)
        except Exception as e:
            _logger.debug("Post-edit hook failed: %s", e)
    return result


# ── Session file modification tracking ────────────────────────────────────────
# Tracks file modification times to detect tampering during the session.
# This prevents plugin/custom-tool injection attacks where the LLM writes a
# malicious file and then tries to load it.

_SESSION_FILE_TIMESTAMPS: dict[str, float] = {}
_SESSION_START_TIME: float = 0.0


def record_session_start() -> None:
    """Record the current time as session start time."""
    global _SESSION_START_TIME
    _SESSION_START_TIME = time.time()


def record_file_timestamp(path: str) -> None:
    """Record a file's modification time at session start."""
    try:
        _SESSION_FILE_TIMESTAMPS[os.path.abspath(path)] = os.path.getmtime(path)
    except OSError:
        pass


def was_file_modified_during_session(path: str) -> bool:
    """Check if a file was modified after the session started.

    Returns True if the file's mtime is newer than the session start time.
    Returns False if the file doesn't exist, can't be checked, or if
    record_session_start() has not been called yet.
    """
    if _SESSION_START_TIME == 0.0:
        return False  # Session start was never recorded — skip check

    try:
        abs_path = os.path.abspath(path)
        mtime = os.path.getmtime(abs_path)

        # If we recorded the timestamp at start, use exact comparison
        if abs_path in _SESSION_FILE_TIMESTAMPS:
            recorded = _SESSION_FILE_TIMESTAMPS[abs_path]
            return abs(mtime - recorded) > 0.1  # Allow small clock skew

        # Fall back to session start time
        return mtime > _SESSION_START_TIME
    except OSError:
        return False  # Can't check — assume not modified


# ── ToolContext ──────────────────────────────────────────────────────────────


@dataclass
class ToolContext:
    """Context passed to every tool execution.

    Provides access to the working directory, file snapshots for undo,
    orchestrator reference for multi-agent support, and path validation.
    """

    working_directory: str
    restart_requested: bool = False
    file_snapshots: dict[str, list[tuple[str, str]]] | None = None
    orchestrator: object | None = None
    """Reference to the Orchestrator for multi-agent support (optional)."""
    agent_id: str = "main"
    """ID of the agent executing this tool (default: 'main')."""
    confirm_edits: bool = False
    """If True, show diff and ask user to confirm before applying file edits."""

    def snapshot_file(self, path: str) -> None:
        """Read the current file content and store a snapshot before modification."""
        if self.file_snapshots is None:
            return
        try:
            with open(path, "r", encoding="utf-8") as _f:
                content = _f.read()
        except FileNotFoundError:
            content = ""
        except Exception:
            return
        timestamp = str(__import__("time").time())
        if path not in self.file_snapshots:
            self.file_snapshots[path] = []
        self.file_snapshots[path].append((timestamp, content))

    def get_snapshots(self, path: str | None = None) -> dict[str, list[tuple[str, str]]]:
        """Get snapshots for a specific path or all paths."""
        if self.file_snapshots is None:
            return {}
        if path is not None:
            return {path: self.file_snapshots.get(path, [])}
        return dict(self.file_snapshots)

    def revert_to_snapshot(self, path: str, index: int = -1) -> bool:
        """Restore a file from a snapshot by index (default: last). Returns True on success."""
        if self.file_snapshots is None or path not in self.file_snapshots:
            return False
        snapshots = self.file_snapshots[path]
        if not snapshots:
            return False
        try:
            _, content = snapshots[index]
            with open(path, "w", encoding="utf-8") as _f:
                _f.write(content)
            return True
        except (IndexError, OSError):
            return False

    def validate_write_path(self, path: str) -> str | None:
        """Validate that a path is within this context's working directory.

        Delegates to ``src.utils.validate_write_path`` (will move to
        ``src.validation`` in Phase 3 of the restructure).
        """
        from src.utils import validate_write_path as _validate
        return _validate(path, self.working_directory)


# ── Tool dataclass ───────────────────────────────────────────────────────────


@dataclass
class Tool:
    """A tool that can be called by the LLM during a conversation.

    Attributes:
        name: Unique tool name used by the LLM.
        description: Natural-language description of what the tool does.
        input_schema: JSON Schema dict describing expected parameters.
        execute: Callable that takes (args, context) and returns a result string.
        read_only: If True, this tool is available in plan/ask modes.
        interactive: If True, this tool pauses for user input.
    """

    name: str
    description: str
    input_schema: dict[str, object]
    execute: Callable[[dict[str, object], ToolContext], str]
    read_only: bool = False
    interactive: bool = False


# ── ToolRegistry ─────────────────────────────────────────────────────────────


class ToolRegistry:
    """Registry of all tools available to the agent.

    Supports registering tools individually, rebuilding from disk
    (reloading all tool modules), and converting to Anthropic's
    tool format for API calls.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a single tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Look up a tool by name."""
        return self._tools.get(name)

    def get_all(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_read_only(self) -> list[Tool]:
        """Return only read-only tools."""
        return [t for t in self._tools.values() if t.read_only]

    def rebuild(self) -> int:
        """Re-discover all tools from scratch by reloading every tool module.

        Clears the current registry and re-imports all tool modules, then
        registers every discovered Tool instance.

        Returns the number of tools registered.
        """
        from src.tools import reload_tools
        self._tools.clear()
        discovered = reload_tools()
        for tool in discovered:
            self._tools[tool.name] = tool
        return len(discovered)

    def to_anthropic_tools(self, *, read_only: bool = False) -> list[dict[str, object]]:
        """Convert registered tools to Anthropic's tool format."""
        tools = self.get_read_only() if read_only else self.get_all()
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]
