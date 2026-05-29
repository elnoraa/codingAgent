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

    def __init__(self, restrict_to_working_directory: str | None = None) -> None:
        self._locals: dict[str, Any] = {}
        self._execution_count = 0
        self._error_count = 0
        self._history: list[str] = []
        self._restrict_to_working_directory = restrict_to_working_directory

    def _make_restricted_globals(self) -> dict[str, Any]:
        """Build a restricted globals namespace that prevents writes outside the working dir."""
        import builtins
        from pathlib import Path

        working_dir = self._restrict_to_working_directory
        if not working_dir:
            return self._locals

        original_open = builtins.open

        def _restricted_open(
            file, mode='r', buffering=-1, encoding=None,
            errors=None, newline=None, closefd=True, opener=None,
        ):
            """Restricted open() — only allows write modes within the working directory."""
            if any(c in mode for c in ('w', 'a', 'x', '+')):
                from src.utils import validate_write_path
                path_str = str(file) if not isinstance(file, str) else file
                error = validate_write_path(path_str, working_dir)
                if error:
                    raise PermissionError(error)
            return original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

        # Create restricted builtins by wrapping the unsafe functions
        restricted_builtins = dict(vars(builtins))
        restricted_builtins['open'] = _restricted_open

        return {'__builtins__': restricted_builtins}

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
                if self._restrict_to_working_directory:
                    # Use restricted globals for the exec
                    restricted_globals = self._make_restricted_globals()
                    exec(compiled, restricted_globals)
                    # Merge back any new variables into self._locals
                    for k, v in restricted_globals.items():
                        if k != '__builtins__':
                            self._locals[k] = v
                else:
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
