from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import types


@dataclass
class ToolContext:
    working_directory: str
    restart_requested: bool = False
    file_snapshots: dict[str, list[tuple[str, str]]] | None = None

    def snapshot_file(self, path: str) -> None:
        """Read the current file content and store a snapshot before modification."""
        import os as _os
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


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, object]
    execute: Callable[[dict[str, object], ToolContext], str]
    read_only: bool = False


def reload_tools() -> list[Tool]:
    """Re-import all tool modules from the tools/ directory and return their Tool objects.

    Scans the tools package directory for Python modules (excluding __init__),
    force-reloads them, and collects any module-level variable ending in ``_tool``
    that is an instance of ``Tool``.
    """
    discovered: list[Tool] = []
    pkg_path = Path(__file__).parent.resolve()

    # Ensure the tools package is in sys.modules
    pkg_name = __name__  # "tools"
    if pkg_name not in sys.modules:
        sys.modules[pkg_name] = sys.modules[__name__]

    # Iterate over all modules in the tools package
    for importer, modname, is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if is_pkg or modname == "__init__":
            continue

        full_modname = f"{pkg_name}.{modname}"

        # If the module was already imported, reload it; otherwise import fresh
        if full_modname in sys.modules:
            mod: types.ModuleType = importlib.reload(sys.modules[full_modname])
        else:
            mod = importlib.import_module(full_modname)

        # Find all Tool instances at module level whose names end with "_tool"
        for name, obj in inspect.getmembers(mod):
            if name.endswith("_tool") and isinstance(obj, Tool):
                discovered.append(obj)

    return discovered


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_all(self) -> list[Tool]:
        return list(self._tools.values())

    def get_read_only(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.read_only]

    def rebuild(self) -> int:
        """Re-discover all tools from scratch by reloading every tool module.

        Clears the current registry and re-imports all tool modules, then
        registers every discovered Tool instance.

        Returns the number of tools registered.
        """
        self._tools.clear()
        discovered = reload_tools()
        for tool in discovered:
            self._tools[tool.name] = tool
        return len(discovered)

    def to_anthropic_tools(self, *, read_only: bool = False) -> list[dict[str, object]]:
        tools = self.get_read_only() if read_only else self.get_all()
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]
