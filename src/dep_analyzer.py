"""Dependency graph / impact analysis using static import analysis.

Given a Python file, shows what other files depend on it and what it
depends on by analyzing imports using the `ast` module.
"""

from __future__ import annotations

import ast
import os

from .logging_config import get_logger

logger = get_logger(__name__)


class ImportGraph:
    """Build and query an import graph for a Python project."""

    def __init__(self) -> None:
        self._imports: dict[str, set[str]] = {}  # file -> set of files it imports
        self._dependents: dict[str, set[str]] = {}  # file -> set of files that import it
        self._built = False

    def build(self, directory: str) -> None:
        """Walk a directory, parse all .py files, and build the import graph."""
        self._imports.clear()
        self._dependents.clear()

        # First pass: find all Python files and their imports
        py_files: dict[str, str] = {}  # module_name -> filepath
        file_imports: dict[str, set[str]] = {}  # filepath -> set of module names

        for root, dirs, files in os.walk(directory):
            # Skip hidden dirs and common non-project dirs
            dirs[:] = [
                d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "venv", ".venv")
            ]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                filepath = os.path.join(root, fname)
                relpath = os.path.relpath(filepath, directory)
                # Map module names to file paths
                module_name = relpath.replace(os.sep, "/").replace(".py", "").replace("/", ".")
                py_files[module_name] = relpath
                py_files[fname.replace(".py", "")] = relpath  # also index by short name

                # Parse imports
                imports = self._parse_imports(filepath)
                if imports:
                    file_imports[relpath] = imports

        # Second pass: resolve module names to file paths
        for filepath, imported_modules in file_imports.items():
            resolved_imports: set[str] = set()
            for mod_name in imported_modules:
                # Try to resolve the module name to a file path
                resolved = self._resolve_module(mod_name, py_files, directory)
                if resolved:
                    resolved_imports.add(resolved)

            self._imports[filepath] = resolved_imports

            # Build reverse mapping (dependents)
            for dep in resolved_imports:
                if dep not in self._dependents:
                    self._dependents[dep] = set()
                self._dependents[dep].add(filepath)

        self._built = True
        logger.info(
            "Import graph built: %d files, %d import relationships",
            len(self._imports),
            sum(len(v) for v in self._imports.values()),
        )

    def _parse_imports(self, filepath: str) -> set[str]:
        """Parse a Python file and extract all imported module names."""
        imports: set[str] = set()
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError, OSError:
            return imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Only take the top-level module
                    top_level = alias.name.split(".")[0]
                    imports.add(top_level)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top_level = node.module.split(".")[0]
                    imports.add(top_level)

        return imports

    def _resolve_module(self, module_name: str, py_files: dict[str, str], directory: str) -> str | None:
        """Try to resolve a module name to a relative file path."""
        # Direct match
        if module_name in py_files:
            return py_files[module_name]

        # Try as package (module/__init__.py)
        for key, path in py_files.items():
            if path.endswith("__init__.py") and key.startswith(module_name):
                return path

        # Try standard library and third-party packages - skip them
        return None

    def get_dependents(self, filepath: str) -> list[str]:
        """Return files that import the given file (direct dependents)."""
        if not self._built:
            return []
        return sorted(self._dependents.get(filepath, set()))

    def get_dependencies(self, filepath: str) -> list[str]:
        """Return files that the given file imports (its dependencies)."""
        if not self._built:
            return []
        return sorted(self._imports.get(filepath, set()))

    def get_all_files(self) -> list[str]:
        """Return all files in the graph."""
        if not self._built:
            return []
        return sorted(set(self._imports.keys()) | set(self._dependents.keys()))

    def clear(self) -> None:
        """Clear the graph."""
        self._imports.clear()
        self._dependents.clear()
        self._built = False
