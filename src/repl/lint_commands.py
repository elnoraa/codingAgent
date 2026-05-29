"""Lint commands — /lint."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.formatting import bold, dim, green

if TYPE_CHECKING:
    from src.repl.repl import Repl


def handle_lint(repl: "Repl", filepath: str) -> None:
    """Run linter on specified file or directory."""
    from src.tools.lint_tool import detect_linter, run_linter

    if not filepath:
        filepath = os.getcwd()

    linter = detect_linter(os.getcwd())
    if linter is None:
        print("  No linter detected.")
        print("  Supported: ruff, flake8, ESLint")
        return

    # Resolve path
    full_path = os.path.join(os.getcwd(), filepath) if not os.path.isabs(filepath) else filepath

    if os.path.isdir(full_path):
        # Lint all supported files in directory
        files: list[str] = []
        for root, dirs, filenames in os.walk(full_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for f in filenames:
                if f.endswith((".py", ".js", ".ts")):
                    files.append(os.path.join(root, f))
    else:
        files = [full_path]

    print(f"  Running {linter} on {len(files)} file(s)...")
    result = run_linter(files, os.getcwd())
    print(f"\n{result}")
