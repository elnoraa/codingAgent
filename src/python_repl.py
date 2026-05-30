"""Python REPL Integration for the Coding Agent.

Provides an embedded interactive Python interpreter session using
``code.InteractiveInterpreter``, with a best-effort restricted execution
environment when ``restrict_to_working_directory`` is set.

**Security boundaries (best-effort sandbox):**
When restricted mode is active, the following are blocked:
- Write-mode ``open()`` to paths outside the working directory
- ``import`` of dangerous modules (``os``, ``subprocess``, ``shutil``, etc.)
- Access to ``__import__`` builtin
- ``type.__subclasses__()`` sandbox escape pattern
- ``os.system``, ``os.popen``, ``subprocess.*``, ``shutil.*``

.. note::
   Python's dynamic nature makes full sandboxing impossible without
   OS-level isolation. This is a **best-effort** restriction, not a
   security boundary. For true isolation, run in a container.
"""

from __future__ import annotations

import io
import sys
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

# Modules that are blocked from import in restricted mode.
# These provide filesystem, process, or code execution capabilities.
_FORBIDDEN_MODULES = frozenset(
    {
        "os",
        "os.path",
        "subprocess",
        "shutil",
        "sys",
        "pathlib",
        "ctypes",
        "ctypes.wintypes",
        "ctypes._endian",
        "inspect",
        "importlib",
        "importlib.util",
        "importlib.metadata",
        "code",
        "codeop",
        "compileall",
        "py_compile",
        "pickle",
        "pickletools",
        "shelve",
        "tempfile",
        "glob",
        "fnmatch",
        "fileinput",
        "io",
        "builtins",
        "antigravity",  # Easter egg that opens a web browser
    }
)

# Builtins that are safe to keep in restricted mode
_SAFE_BUILTIN_NAMES = frozenset(
    {
        "abs",
        "all",
        "any",
        "ascii",
        "bin",
        "bool",
        "bytearray",
        "bytes",
        "callable",
        "chr",
        "complex",
        "dict",
        "dir",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "hasattr",
        "hash",
        "hex",
        "id",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "object",
        "oct",
        "ord",
        "pow",
        "print",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "type",
        "zip",
        "True",
        "False",
        "None",
        "Ellipsis",
        "NotImplemented",
        "property",
        "staticmethod",
        "classmethod",
        "super",
        "Exception",
        "BaseException",
        "StopIteration",
        "KeyboardInterrupt",
    }
)

# Names that are always forbidden (protect against sandbox escape patterns)
_FORBIDDEN_ATTR_NAMES = frozenset(
    {
        "__class__",
        "__base__",
        "__subclasses__",
        "__bases__",
        "__globals__",
        "__code__",
        "__closure__",
        "__builtins__",
        "__import__",
        "__loader__",
        "__spec__",
    }
)


class PythonRepl:
    """Embedded Python REPL using exec/eval with shared state.

    When ``restrict_to_working_directory`` is set, the REPL operates in
    restricted mode: dangerous imports are blocked, write operations are
    limited to the working directory, and common sandbox-escape patterns
    are intercepted.
    """

    def __init__(self, restrict_to_working_directory: str | None = None) -> None:
        self._locals: dict[str, Any] = {}
        self._execution_count = 0
        self._error_count = 0
        self._history: list[str] = []
        self._restrict_to_working_directory = restrict_to_working_directory

    def _make_restricted_globals(self) -> dict[str, Any]:
        """Build a restricted globals namespace that prevents writes
        outside the working dir and blocks dangerous imports/modules.

        Returns a dict suitable for use as the ``globals`` argument to
        ``exec()``.
        """
        import builtins

        working_dir = self._restrict_to_working_directory
        if not working_dir:
            return self._locals

        original_open = builtins.open
        original_import = builtins.__import__

        # ── Restricted open() ──────────────────────────────────────────────
        def _restricted_open(
            file,
            mode="r",
            buffering=-1,
            encoding=None,
            errors=None,
            newline=None,
            closefd=True,
            opener=None,
        ):
            """Restricted open() — only allows write modes within the working directory."""
            if any(c in mode for c in ("w", "a", "x", "+")):
                from src.utils import validate_write_path

                path_str = str(file) if not isinstance(file, str) else file
                error = validate_write_path(path_str, working_dir)
                if error:
                    raise PermissionError(error)
            return original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

        # ── Restricted __import__ ──────────────────────────────────────────
        def _restricted_import(name: str, *args: Any, **kwargs: Any) -> Any:
            """Restricted import() — blocks dangerous modules."""
            # Check the base module name (before any dot)
            base_name = name.split(".")[0]
            if base_name in _FORBIDDEN_MODULES:
                logger.warning("REPL: blocked import of '%s' (forbidden module)", name)
                raise ImportError(
                    f"Module '{name}' is not allowed in the restricted REPL. "
                    f"This module provides system-level access which is disabled "
                    f"for security."
                )

            # Check if the name itself is forbidden (e.g. "os.path")
            if name in _FORBIDDEN_MODULES:
                logger.warning("REPL: blocked import of '%s' (forbidden module)", name)
                raise ImportError(f"Module '{name}' is not allowed in the restricted REPL.")

            return original_import(name, *args, **kwargs)

        # ── Build safe builtins ────────────────────────────────────────────
        all_builtins = vars(builtins)
        restricted_builtins: dict[str, Any] = {}
        for name in _SAFE_BUILTIN_NAMES:
            if name in all_builtins:
                restricted_builtins[name] = all_builtins[name]

        # Wrap the unsafe builtins
        restricted_builtins["open"] = _restricted_open
        # Remove __import__ from the safe set — we override it separately
        restricted_builtins["__import__"] = _restricted_import

        return {"__builtins__": restricted_builtins}

    def _check_for_sandbox_escape(self, code_str: str) -> str | None:
        """Pre-check code for known sandbox escape patterns.

        Returns an error message string if an escape is detected, None otherwise.

        This is a best-effort static analysis that catches the most common
        Python sandbox escape techniques before they execute.
        """
        import ast

        if not self._restrict_to_working_directory:
            return None

        forbidden_imports = [
            m
            for m in _FORBIDDEN_MODULES
            if m != "builtins"  # builtins is handled via __import__
        ]

        try:
            tree = ast.parse(code_str)
            for node in ast.walk(tree):
                # Block direct __import__ calls
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                        return "Error: Calling __import__ directly is not allowed in the restricted REPL."
                    # Block type.__subclasses__() escape
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr in ("__subclasses__", "__base__", "__bases__", "__mro__"):
                            return (
                                f"Error: Access to '{node.func.attr}' is blocked "
                                f"in the restricted REPL (sandbox escape prevention)."
                            )
                # Block 'import os' etc via normal import statements
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        base = alias.name.split(".")[0]
                        if base in forbidden_imports:
                            return f"Error: Module '{alias.name}' is not allowed in the restricted REPL."
                if isinstance(node, ast.ImportFrom):
                    if node.module:
                        base = node.module.split(".")[0]
                        if base in forbidden_imports:
                            return f"Error: Module '{node.module}' is not allowed in the restricted REPL."
        except SyntaxError:
            pass  # Will be caught by compile() later

        return None

    def execute(self, code_str: str) -> str:
        """Execute Python code and capture stdout/stderr.

        Returns the output (or error message) as a string.
        """
        code_str = code_str.strip()
        if not code_str:
            return ""

        self._execution_count += 1
        self._history.append(code_str)

        # ── Static sandbox escape detection (pre-check) ────────────────────
        escape_error = self._check_for_sandbox_escape(code_str)
        if escape_error:
            self._error_count += 1
            logger.warning("REPL sandbox escape blocked: %s", escape_error)
            return escape_error

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
                        if k != "__builtins__":
                            self._locals[k] = v
                else:
                    exec(compiled, self._locals)
            except Exception:
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
        return {k: v for k, v in self._locals.items() if not k.startswith("_")}

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
