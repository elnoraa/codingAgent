from __future__ import annotations

import os
import subprocess
from typing import Any

from tools import Tool, ToolContext


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    root_dir = args.get("path") or os.getcwd()
    command = args.get("command") or ""
    timeout = int(args.get("timeout", 120))

    # If no explicit command, try to auto-detect test framework
    if not command:
        command = _detect_test_command(root_dir)

    if not command:
        return (
            "[Error] Could not auto-detect test framework. "
            "Please specify a command explicitly (e.g. 'pytest', 'go test ./...', 'npm test')."
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=root_dir,
        )
    except subprocess.TimeoutExpired:
        return f"[Error] Tests timed out after {timeout}s"
    except Exception as exc:
        return f"[Error] {exc}"

    output_parts: list[str] = []

    # Summary line
    if result.returncode == 0:
        output_parts.append("✅ All tests passed!")
    else:
        output_parts.append(f"❌ Tests failed (exit code: {result.returncode})")

    # Stdout (trimmed if too long)
    stdout = result.stdout.rstrip("\n")
    if stdout:
        lines = stdout.split("\n")
        if len(lines) > 200:
            stdout = "\n".join(lines[:100]) + f"\n... ({len(lines) - 100} more lines)" + "\n".join(lines[-100:])
        output_parts.append(stdout)

    # Stderr
    if result.stderr:
        stderr = result.stderr.rstrip("\n")
        if len(stderr) > 1000:
            stderr = stderr[:1000] + "..."
        output_parts.append(f"[stderr]\n{stderr}")

    return "\n".join(output_parts)


def _detect_test_command(workdir: str) -> str:
    """Detect which test framework is being used."""
    files: set[str] = set()
    try:
        for entry in os.scandir(workdir):
            files.add(entry.name)
    except Exception:
        return ""

    # Check for common config files
    if "pyproject.toml" in files or "setup.cfg" in files or "setup.py" in files:
        return "python -m pytest -v 2>&1 || python -m unittest discover -v 2>&1 || echo 'No test runner found'"

    if "package.json" in files:
        return "npm test 2>&1 || echo 'No test script found in package.json'"

    if "go.mod" in files or any(f.endswith(".go") for f in files if os.path.isfile(os.path.join(workdir, f))):
        return "go test ./... 2>&1 || echo 'No Go tests found'"

    if "Cargo.toml" in files:
        return "cargo test 2>&1 || echo 'No Rust tests found'"

    if "Makefile" in files or "makefile" in files:
        return "make test 2>&1 || echo 'No test target in Makefile'"

    return ""


run_tests_tool = Tool(
    name="run_tests",
    description=(
        "Run tests for the project. If no command is specified, it will "
        "auto-detect the test framework (pytest/unittest for Python, npm test "
        "for Node.js, go test for Go, cargo test for Rust). Returns test "
        "output and a pass/fail summary."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Explicit test command to run (e.g. 'pytest tests/', 'npm run test'). "
                "If empty, auto-detects the framework.",
            },
            "path": {
                "type": "string",
                "description": "Project directory (defaults to current directory)",
            },
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds (default: 120)",
            },
        },
    },
    execute=execute,
)
