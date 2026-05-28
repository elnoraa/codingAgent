from __future__ import annotations

import logging
import subprocess
from typing import Any

from tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 30


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    command = args.get("command")
    timeout = int(args.get("timeout", DEFAULT_TIMEOUT))
    workdir = args.get("workdir") or None
    logger.info("execute: command=%s, timeout=%s, workdir=%s", command, timeout, workdir)
    if not command:
        return 'Error: missing required argument "command".'

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
        logger.warning("Command timed out after %ds: %s", timeout, command)
        return f"[Error] Command timed out after {timeout}s"
    except Exception as exc:
        logger.error("Command failed: %s", exc)
        return f"[Error] {exc}"

    parts: list[str] = []
    if result.stdout:
        parts.append(result.stdout.rstrip("\n"))
    if result.stderr:
        parts.append(f"[stderr]\n{result.stderr.rstrip(chr(10))}")
    if result.returncode != 0:
        parts.append(f"\n[Exit code: {result.returncode}]")

    logger.info("Command completed (exit_code=%d, stdout_len=%d, stderr_len=%d)", result.returncode, len(result.stdout or ""), len(result.stderr or ""))
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
