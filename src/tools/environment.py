"""Environment inspection tool.

Shows Python version, installed packages, OS information, and other
runtime details that help the agent understand its execution context.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from typing import Any

from src.tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    show_packages = bool(args.get("packages", False))

    lines: list[str] = []
    lines.append("Runtime Environment:")
    lines.append("")
    lines.append(f"  Python:      {sys.version.split()[0]} ({platform.architecture()[0]})")
    lines.append(f"  Platform:    {platform.platform()}")
    lines.append(f"  OS:          {platform.system()} {platform.release()}")
    lines.append(f"  Hostname:    {platform.node()}")
    lines.append(f"  CWD:         {os.getcwd()}")

    # Try to get pip version
    try:
        pip_result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if pip_result.returncode == 0:
            pip_version = pip_result.stdout.split()[1]
            lines.append(f"  pip:         {pip_version}")
    except Exception:
        pass

    # Show current environment variables prefix (for debugging config)
    agent_vars = {k: v for k, v in os.environ.items() if k.startswith("CODING_AGENT_")}
    if agent_vars:
        lines.append("")
        lines.append("Agent Environment Variables:")
        for key in sorted(agent_vars):
            lines.append(f"  {key}={agent_vars[key]}")

    if show_packages:
        lines.append("")
        lines.append("Installed Packages:")
        try:
            pkg_result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=columns"],
                capture_output=True, text=True, timeout=30,
            )
            if pkg_result.returncode == 0:
                pkg_lines = pkg_result.stdout.strip().split("\n")
                # Skip header lines
                for line in pkg_lines[2:]:
                    if line.strip():
                        lines.append(f"  {line.strip()}")
        except Exception:
            lines.append("  (could not list packages)")

    return "\n".join(lines)


environment_tool = Tool(
    name="environment",
    description=(
        "Show the runtime environment: Python version, operating system, "
        "working directory, pip version, and optionally installed packages. "
        "Useful for understanding available tools, library versions, and platform "
        "constraints. Use packages=true to list installed Python packages."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "packages": {
                "type": "boolean",
                "description": "If true, also list all installed Python packages (default: false)",
            },
        },
    },
    execute=execute,
    read_only=True,
)
