"""Compatibility shim — re-exports from src.tools for external plugins.

This allows external plugins (e.g., in plugins/ directory) to continue
using ``from tools import Tool, ToolContext`` after the tools package
was moved into src/tools/.
"""
from src.tools import (  # noqa: F401
    Tool,
    ToolContext,
    ToolRegistry,
    register_post_edit_hook,
    run_post_edit_hooks,
    record_session_start,
    record_file_timestamp,
    was_file_modified_during_session,
    _reload_src_modules,
    reload_tools,
)
