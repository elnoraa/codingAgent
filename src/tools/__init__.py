"""Tool package — individual tool modules and reloading logic.

Each module in this package defines a ``*_tool`` variable that is an
instance of ``Tool``.  The ``reload_tools()`` function scans this package
and returns all discovered tools, enabling hot-reloading via ``/reload``.

Core data types (``Tool``, ``ToolContext``, ``ToolRegistry``) are defined
in :mod:`src.tool_base` and re-exported here for backward compatibility.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from src.tool_base import (
    Tool,
    ToolContext,
    ToolRegistry,
    record_file_timestamp,
    record_session_start,
    register_post_edit_hook,
    run_post_edit_hooks,
    was_file_modified_during_session,
)

if TYPE_CHECKING:
    import types

_logger = logging.getLogger(__name__)


def _reload_src_modules() -> None:
    """Reload src.* modules in dependency order so tool modules see fresh code.

    When the agent modifies its own source code (e.g., src/plan.py) and then
    triggers a reload (via /reload or restart_session), the changes exist only
    on disk. Python's module cache still holds the old version. This function
    force-reloads the commonly-modified modules in dependency order so that
    subsequent tool module reloads import from the updated code.
    """
    # Reload in dependency order (modules with no src.* deps first)
    _modules = [
        "src.logging_config",  # no src.* dependencies
        "src.mode",  # no src.* dependencies
        "src.plan",  # depends on src.logging_config
        "src.session",  # depends on src.logging_config
        "src.profiles",  # depends on src.logging_config
        "src.notifications",  # depends on src.logging_config
        "src.prompts",  # depends on src.mode
        "src.python_repl",  # depends on src.logging_config
        "src.client",  # depends on src.logging_config
    ]
    for mod_name in _modules:
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                _logger.warning("Failed to reload module: %s", mod_name, exc_info=True)


def reload_tools() -> list[Tool]:
    """Re-import all tool modules from the tools/ directory and return their Tool objects.

    Scans the tools package directory for Python modules (excluding __init__),
    force-reloads them, and collects any module-level variable ending in ``_tool``
    that is an instance of ``Tool``.
    """
    _reload_src_modules()

    discovered: list[Tool] = []
    pkg_path = Path(__file__).parent.resolve()

    # Ensure the tools package is in sys.modules
    pkg_name = __name__  # "src.tools"
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
