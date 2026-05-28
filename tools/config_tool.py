"""Agent configuration introspection tool.

Shows the agent its own configuration: mode, model, max_tokens,
working directory, and other operating parameters. The REPL sets
environment variables before each turn which this tool reads.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(_args: dict[str, Any], ctx: ToolContext) -> str:
    lines: list[str] = []
    lines.append("Agent Configuration:")
    lines.append("")
    lines.append(f"  Working directory: {ctx.working_directory}")
    lines.append(f"  Python version:    {sys.version.split()[0]}")

    # Read values set by the REPL before each turn
    mode = os.environ.get("CODING_AGENT_MODE", "unknown")
    model = os.environ.get("CODING_AGENT_MODEL", "unknown")
    max_tokens = os.environ.get("CODING_AGENT_MAX_TOKENS", "unknown")
    temperature = os.environ.get("CODING_AGENT_TEMPERATURE", "unknown")
    persona = os.environ.get("CODING_AGENT_PERSONA", "")

    lines.append(f"  Mode:              {mode}")
    lines.append(f"  Model:             {model}")
    lines.append(f"  Max tokens:        {max_tokens}")
    lines.append(f"  Temperature:       {temperature}")
    if persona:
        lines.append(f"  Custom persona:    {persona[:60]}{'...' if len(persona) > 60 else ''}")

    return "\n".join(lines)


config_tool = Tool(
    name="config",
    description=(
        "Show the agent's current configuration: active mode (code/plan/ask), "
        "model name, max tokens, temperature, working directory, and custom persona. "
        "Useful for self-diagnosis and understanding your current operating parameters."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=execute,
    read_only=True,
)
