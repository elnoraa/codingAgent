"""Plugin system for loading third-party tools and hooks."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
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

    def load_plugin(self, name: str) -> PluginInfo | None:
        """Load a single plugin by name."""
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
