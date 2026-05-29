"""Plugin system for loading third-party tools and hooks."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from tools import Tool, ToolContext
from .logging_config import get_logger

logger = get_logger(__name__)

# Plugin hook types
PluginHook = Callable[..., Any]

# Plugin directory
PLUGINS_DIR = Path("plugins")


@dataclass
class PluginInfo:
    """Information about a loaded plugin."""
    name: str
    version: str
    description: str
    author: str
    module_path: str
    tools: list[Tool]
    hooks: dict[str, list[PluginHook]]


class PluginLoader:
    """Discovers and loads plugins from the plugins directory."""

    def __init__(self, plugins_dir: str | Path | None = None):
        self._plugins_dir = Path(plugins_dir or PLUGINS_DIR)
        self._plugins: dict[str, PluginInfo] = {}
        self._hooks: dict[str, list[PluginHook]] = {
            "on_startup": [],
            "on_shutdown": [],
            "before_tool_call": [],
            "after_tool_call": [],
        }

    def discover_plugins(self) -> list[str]:
        """Scan the plugins directory and return discovered plugin names."""
        if not self._plugins_dir.exists():
            logger.info("Plugins directory not found: %s", self._plugins_dir)
            return []

        plugins: list[str] = []
        for entry in self._plugins_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith(("__", ".")):
                plugin_file = entry / "plugin.py"
                if plugin_file.exists():
                    plugins.append(entry.name)
                elif (entry / "__init__.py").exists():
                    plugins.append(entry.name)

        return sorted(plugins)

    def load_plugin(self, name: str, interactive: bool = True) -> PluginInfo | None:
        """Load a single plugin by name.

        Args:
            name: Plugin directory name.
            interactive: If True, show plugin metadata and prompt for user
                confirmation before loading. Set to False for programmatic
                access (e.g., tests).

        If the plugin has been previously approved (its file hash matches
        the allowlist), the confirmation prompt is skipped.
        """
        plugin_dir = self._plugins_dir / name

        # Find the plugin entry point
        entry_points = [
            plugin_dir / "plugin.py",
            plugin_dir / "__init__.py",
        ]

        entry_point = None
        for ep in entry_points:
            if ep.exists():
                entry_point = ep
                break

        if entry_point is None:
            logger.warning("Plugin '%s' has no entry point (plugin.py or __init__.py)", name)
            return None

        # ── User confirmation ──────────────────────────────────────────────
        if interactive:
            file_hash = self._hash_file(entry_point)
            allowlist = self._get_allowlist()
            if allowlist.get(name) != file_hash:
                # Read metadata without executing the module first
                metadata = self._extract_metadata_from_source(entry_point)
                print()
                print(f"  {'─' * 60}")
                print(f"  ⚠  Plugin detected: {name}")
                print(f"     Author:    {metadata.get('author', 'unknown')}")
                print(f"     Version:   {metadata.get('version', '0.1.0')}")
                print(f"     Description: {metadata.get('description', 'No description')}")
                print(f"     Path:      {entry_point}")
                print()
                print(f"  Load this plugin? It will have full access to your system.")
                response = input("  [y/N] ").strip().lower()
                if response not in ("y", "yes"):
                    logger.info("Plugin '%s' loading denied by user", name)
                    print(f"  Plugin '{name}' not loaded.")
                    return None
                # Record approval in allowlist
                self._update_allowlist(name, file_hash)
                print(f"  Plugin '{name}' approved (remembered for next time).")
                print(f"  {'─' * 60}")
                print()

        try:
            # Add plugin directory to sys.path for imports
            plugin_parent = str(plugin_dir.parent)
            if plugin_parent not in sys.path:
                sys.path.insert(0, plugin_parent)

            # Load the module
            module_name = f"plugins.{name}.plugin" if entry_point.name == "plugin.py" else f"plugins.{name}"

            if module_name in sys.modules:
                mod = importlib.reload(sys.modules[module_name])
            else:
                spec = importlib.util.spec_from_file_location(module_name, str(entry_point))
                if spec is None or spec.loader is None:
                    return None
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)

            # Extract plugin metadata
            plugin_info = self._extract_plugin_info(mod, name, str(entry_point))
            self._plugins[name] = plugin_info

            # Register hooks
            self._register_hooks(name, plugin_info)

            logger.info("Loaded plugin: %s v%s", name, plugin_info.version)
            return plugin_info

        except Exception as e:
            logger.error("Failed to load plugin '%s': %s", name, e, exc_info=True)
            return None

    def _hash_file(self, path: Path) -> str:
        """Return the SHA-256 hex digest of a file."""
        import hashlib
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def _get_allowlist(self) -> dict[str, str]:
        """Load the plugin allowlist (maps plugin name to file hash)."""
        allowlist_path = self._plugins_dir / ".plugin-allowlist.json"
        if allowlist_path.exists():
            try:
                return json.loads(allowlist_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _update_allowlist(self, name: str, file_hash: str) -> None:
        """Add a plugin to the allowlist so it can load silently next time."""
        allowlist = self._get_allowlist()
        allowlist[name] = file_hash
        allowlist_path = self._plugins_dir / ".plugin-allowlist.json"
        allowlist_path.write_text(json.dumps(allowlist, indent=2), encoding="utf-8")

    def _extract_metadata_from_source(self, entry_point: Path) -> dict[str, str]:
        """Read plugin metadata (author, version, description) from source without executing.

        Parses ``__author__``, ``__version__``, and ``__description__``
        module-level string assignments using the AST module.
        """
        import ast
        metadata: dict[str, str] = {}
        try:
            tree = ast.parse(entry_point.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in ("__author__", "__version__", "__description__"):
                            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                                metadata[target.id] = node.value.value
        except (SyntaxError, OSError):
            pass
        return metadata

    def _extract_plugin_info(self, mod: Any, name: str, module_path: str) -> PluginInfo:
        """Extract plugin metadata from module."""
        return PluginInfo(
            name=name,
            version=getattr(mod, "__version__", "0.1.0"),
            description=getattr(mod, "__description__", ""),
            author=getattr(mod, "__author__", ""),
            module_path=module_path,
            tools=self._discover_tools(mod),
            hooks=self._discover_hooks(mod),
        )

    def _discover_tools(self, mod: Any) -> list[Tool]:
        """Discover Tool instances in a plugin module."""
        tools: list[Tool] = []
        for _, obj in inspect.getmembers(mod):
            if isinstance(obj, Tool):
                tools.append(obj)
        return tools

    def _discover_hooks(self, mod: Any) -> dict[str, list[PluginHook]]:
        """Discover hook functions in a plugin module."""
        hooks: dict[str, list[PluginHook]] = {}
        for hook_name in self._hooks:
            func_name = f"on_{hook_name}" if not hook_name.startswith("on_") else hook_name
            func = getattr(mod, func_name, None)
            if func and callable(func):
                hooks.setdefault(hook_name, []).append(func)
        return hooks

    def _register_hooks(self, name: str, plugin: PluginInfo) -> None:
        """Register all hooks from a plugin."""
        for hook_name, hook_funcs in plugin.hooks.items():
            if hook_name in self._hooks:
                self._hooks[hook_name].extend(hook_funcs)

    def load_all_plugins(self, enabled: list[str] | None = None) -> list[PluginInfo]:
        """Load all discovered plugins, optionally filtering by enabled list."""
        discovered = self.discover_plugins()
        loaded: list[PluginInfo] = []

        for name in discovered:
            if enabled is not None and name not in enabled:
                logger.info("Skipping disabled plugin: %s", name)
                continue
            plugin = self.load_plugin(name)
            if plugin:
                loaded.append(plugin)

        return loaded

    def get_plugin(self, name: str) -> PluginInfo | None:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def get_all_plugins(self) -> list[PluginInfo]:
        """Get all loaded plugins."""
        return list(self._plugins.values())

    def run_hooks(self, hook_name: str, *args: Any, **kwargs: Any) -> None:
        """Run all registered hooks of a given type."""
        for hook in self._hooks.get(hook_name, []):
            try:
                hook(*args, **kwargs)
            except Exception as e:
                logger.error("Hook '%s' failed: %s", hook_name, e)

    def get_tools(self) -> list[Tool]:
        """Get all tools from all loaded plugins."""
        tools: list[Tool] = []
        for plugin in self._plugins.values():
            tools.extend(plugin.tools)
        return tools

    def unload_all(self) -> None:
        """Unload all plugins and clear hooks."""
        self.run_hooks("on_shutdown")
        self._plugins.clear()
        for hook_name in self._hooks:
            self._hooks[hook_name].clear()
