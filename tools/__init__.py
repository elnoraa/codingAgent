"""Compatibility shim — re-exports from src.tool_base and src.tools for external plugins.

Allows external plugins (e.g., in plugins/ directory) to continue
using ``from tools import Tool, ToolContext`` after the tools package
was moved into src/tools/.
"""
from src.tool_base import (  # noqa: F401
    Tool,
    ToolContext,
    ToolRegistry,
    register_post_edit_hook,
    run_post_edit_hooks,
    record_session_start,
    record_file_timestamp,
    was_file_modified_during_session,
)
from src.tools import (  # noqa: F401
    _reload_src_modules,
    reload_tools,
)
