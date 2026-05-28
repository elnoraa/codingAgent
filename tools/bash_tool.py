from __future__ import annotations

import subprocess
from typing import Any

from tools import Tool, ToolContext

DEFAULT_TIMEOUT = 30


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    command = args.get("command")
    if not command:
        return 'Error: missing required argument "command".'

    timeout = int(args.get("timeout", DEFAULT_TIMEOUT))
    workdir = args.get("workdir") or None

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired:
        return f"[Error] Command timed out after {timeout}s"
    except Exception as exc:
        return f"[Error] {exc}"

    parts: list[str] = []
    if result.stdout:
        parts.append(result.stdout.rstrip("\n"))
    if result.stderr:
        parts.append(f"[stderr]\n{result.stderr.rstrip(chr(10))}")
    if result.returncode != 0:
        parts.append(f"\n[Exit code: {result.returncode}]")

    return "\n".join(parts) if parts else "Command completed with no output."


bash_tool = Tool(
    name="bash",
    description=(
        "Run a shell command and return its output. Use this to compile, "
        "run tests, lint, install packages, or any other shell operation."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "timeout": {"type": "number", "description": "Timeout in seconds (default: 30)"},
            "workdir": {
                "type": "string",
                "description": "Working directory for the command (default: project root)",
            },
        },
        "required": ["command"],
    },
    execute=execute,
)
