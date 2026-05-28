"""Python REPL Integration for the Coding Agent.

Provides an embedded interactive Python interpreter session using
`code.InteractiveInterpreter`. Tracks execution count, variable state,
and error history. Variables persist across executions within a session.
"""

from __future__ import annotations

import io
import logging
import sys
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)


class PythonRepl:
    """Embedded Python REPL using exec/eval with shared state."""

    def __init__(self) -> None:
        self._locals: dict[str, Any] = {}
        self._execution_count = 0
        self._error_count = 0
        self._history: list[str] = []

    def execute(self, code_str: str) -> str:
        """Execute Python code and capture stdout/stderr.

        Returns the output (or error message) as a string.
        """
        code_str = code_str.strip()
        if not code_str:
            return ""

        self._execution_count += 1
        self._history.append(code_str)

        # Capture stdout and stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()

        try:
            sys.stdout = captured_stdout
            sys.stderr = captured_stderr

            # Try compiling to detect syntax errors first
            try:
                compiled = compile(code_str, "<repl>", "exec")
            except SyntaxError as e:
                self._error_count += 1
                captured_stderr.write(f"SyntaxError: {e}\n")
                return captured_stderr.getvalue().strip()

            # Execute with the shared locals dictionary
            try:
                exec(compiled, self._locals)
            except Exception as e:
                self._error_count += 1
                import traceback
                traceback.print_exc(file=captured_stderr)

            output = captured_stdout.getvalue()
            error_output = captured_stderr.getvalue()

            if error_output:
                return error_output.strip()

            return output.strip()

        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    def get_variables(self) -> dict[str, Any]:
        """Return current variable state (excluding builtins and internals)."""
        return {
            k: v
            for k, v in self._locals.items()
            if not k.startswith("_")
        }

    def reset(self) -> None:
        """Reset the REPL state, clearing all variables."""
        self._locals.clear()
        self._execution_count = 0
        self._error_count = 0
        self._history.clear()

    @property
    def execution_count(self) -> int:
        return self._execution_count

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def history(self) -> list[str]:
        return list(self._history)
