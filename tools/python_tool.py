"""Python execution tool for the Coding Agent.

Allows executing Python code snippets within the agent session.
The tool maintains shared state across executions.
"""

from __future__ import annotations

from tools import Tool, ToolContext

_python_repl_instance: "PythonRepl | None" = None  # type: ignore[name-defined]


def _get_repl() -> "PythonRepl":  # type: ignore[name-defined]
    """Get or create the shared PythonRepl instance."""
    global _python_repl_instance
    if _python_repl_instance is None:
        from src.python_repl import PythonRepl
        _python_repl_instance = PythonRepl()
    return _python_repl_instance


def _execute_python(args: dict[str, object], ctx: ToolContext) -> str:
    """Execute Python code and return the output."""
    code_str = args.get("code", "")
    if not isinstance(code_str, str) or not code_str.strip():
        return "Error: No code provided. Use {\"code\": \"...\"}."

    repl = _get_repl()
    return repl.execute(code_str)


python_tool = Tool(
    name="python",
    description="Execute Python code in an embedded REPL. Variables persist across calls. Returns stdout/stderr output.",
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            }
        },
        "required": ["code"],
    },
    execute=_execute_python,
)
