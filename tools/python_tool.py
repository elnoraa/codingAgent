"""Python execution tool for the Coding Agent.

Allows executing Python code snippets within the agent session.
The tool maintains shared state across executions.

WARNING: File writes via open() are restricted to the project's working
directory. Writes outside the working directory will raise PermissionError.
"""

from __future__ import annotations

from tools import Tool, ToolContext

_python_repl_instance: "PythonRepl | None" = None  # type: ignore[name-defined]


def _get_repl(ctx: ToolContext | None = None) -> "PythonRepl":  # type: ignore[name-defined]
    """Get or create the shared PythonRepl instance."""
    global _python_repl_instance
    if _python_repl_instance is None:
        from src.python_repl import PythonRepl
        working_dir = ctx.working_directory if ctx else None
        _python_repl_instance = PythonRepl(restrict_to_working_directory=working_dir)
    return _python_repl_instance


def _execute_python(args: dict[str, object], ctx: ToolContext) -> str:
    """Execute Python code and return the output."""
    code_str = args.get("code", "")
    if not isinstance(code_str, str) or not code_str.strip():
        return "Error: No code provided. Use {\"code\": \"...\"}."

    # Validate code length
    from src.utils import validate_length, MAX_CODE_LENGTH
    error = validate_length(code_str, MAX_CODE_LENGTH, "Python code")
    if error:
        return error

    repl = _get_repl(ctx)
    return repl.execute(code_str)


python_tool = Tool(
    name="python",
    description=(
        "Execute Python code in an embedded REPL. Variables persist across calls. "
        "Returns stdout/stderr output.\n\n"
        "WARNING: File writes via open() are restricted to the project's working "
        "directory. Attempts to write outside will raise PermissionError."
    ),
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
    read_only=False,
)
