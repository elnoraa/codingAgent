"""Custom Tools via Config for the Coding Agent.

Allows users to define custom tools through a JSON config file
without writing Python code. Supports handler types: bash, http, python.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from .logging_config import get_logger
from tools import Tool, ToolContext

logger = get_logger(__name__)


@dataclass
class CustomToolDef:
    """Definition of a custom tool from config."""
    name: str
    description: str
    input_schema: dict[str, object]
    handler_type: str  # "bash", "http", "python"
    handler_config: dict[str, Any] = field(default_factory=dict)


def _handle_bash_tool(args: dict[str, object], ctx: ToolContext, defn: CustomToolDef) -> str:
    """Execute a bash command with template substitution."""
    command_template = defn.handler_config.get("command", "")
    if not command_template:
        return "Error: No command specified in tool definition."

    # Template substitution: {{param_name}} -> args["param_name"]
    try:
        command = command_template
        for key, value in args.items():
            command = command.replace("{{" + key + "}}", str(value))
    except Exception as e:
        return f"Error in template substitution: {e}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=ctx.working_directory,
        )
        output = ""
        if result.stdout:
            output += result.stdout.strip()
        if result.stderr:
            if output:
                output += "\n"
            output += result.stderr.strip()
        if result.returncode != 0:
            output = f"Error (exit code {result.returncode}): {output}"
        return output or f"Command completed (exit code {result.returncode})."
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except (OSError, subprocess.SubprocessError) as e:
        return f"Error executing command: {e}"


def _handle_http_tool(args: dict[str, object], ctx: ToolContext, defn: CustomToolDef) -> str:
    """Make an HTTP request."""
    url_template = defn.handler_config.get("url", "")
    method = defn.handler_config.get("method", "GET").upper()
    if not url_template:
        return "Error: No URL specified in tool definition."

    # Template substitution for URL
    try:
        url = url_template
        for key, value in args.items():
            url = url.replace("{{" + key + "}}", str(value))
    except Exception as e:
        return f"Error in URL template substitution: {e}"

    try:
        import urllib.request
        import urllib.error
        import urllib.parse

        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            return f"HTTP {response.status}:\n{body[:2000]}"
    except Exception as e:
        return f"HTTP Error: {e}"


def _handle_python_tool(args: dict[str, object], ctx: ToolContext, defn: CustomToolDef) -> str:
    """Execute embedded Python script with args as variables."""
    script = defn.handler_config.get("script", "")
    if not script:
        return "Error: No script specified in tool definition."

    import io
    import sys as _sys

    old_stdout = _sys.stdout
    old_stderr = _sys.stderr
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()

    try:
        _sys.stdout = captured_stdout
        _sys.stderr = captured_stderr

        # Make args available as variables in the script namespace
        local_vars: dict[str, Any] = dict(args)
        exec(script, local_vars)

        output = captured_stdout.getvalue()
        error_output = captured_stderr.getvalue()
        result = ""
        if output.strip():
            result += output.strip()
        if error_output.strip():
            if result:
                result += "\n"
            result += error_output.strip()
        return result or "Script completed."
    except Exception as e:
        return f"Error executing script: {e}"
    finally:
        _sys.stdout = old_stdout
        _sys.stderr = old_stderr


def _make_execute(defn: CustomToolDef) -> Any:
    """Create an execute function for a custom tool definition."""
    if defn.handler_type == "bash":
        return lambda args, ctx: _handle_bash_tool(args, ctx, defn)
    elif defn.handler_type == "http":
        return lambda args, ctx: _handle_http_tool(args, ctx, defn)
    elif defn.handler_type == "python":
        return lambda args, ctx: _handle_python_tool(args, ctx, defn)
    else:
        raise ValueError(f"Unknown handler type: {defn.handler_type}")


def load_custom_tools(config_path: str | None, working_directory: str) -> list[Tool]:
    """Load custom tools from a config file.

    The config_path can be absolute or relative to working_directory.
    Returns a list of Tool objects.
    """
    if not config_path:
        return []

    # Resolve the config path
    if not os.path.isabs(config_path):
        config_path = os.path.join(working_directory, config_path)

    if not os.path.isfile(config_path):
        logger.info("Custom tools config not found: %s", config_path)
        return []

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to load custom tools config: %s", e)
        return []

    raw_tools: list[dict[str, Any]] = data.get("tools", [])
    if not raw_tools:
        return []

    tools: list[Tool] = []
    for raw in raw_tools:
        try:
            name = raw.get("name", "")
            if not name:
                logger.warning("Skipping custom tool with empty name")
                continue
            description = raw.get("description", "")
            input_schema = raw.get("input_schema", {"type": "object", "properties": {}})
            handler = raw.get("handler", {})
            handler_type = handler.get("type", "bash")
            handler_config = {k: v for k, v in handler.items() if k != "type"}

            defn = CustomToolDef(
                name=name,
                description=description,
                input_schema=input_schema,
                handler_type=handler_type,
                handler_config=handler_config,
            )

            tool = Tool(
                name=name,
                description=description,
                input_schema=input_schema,
                execute=_make_execute(defn),
            )
            tools.append(tool)
            logger.info("Loaded custom tool: %s (type=%s)", name, handler_type)
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Skipping invalid custom tool definition: %s", e)
            continue

    return tools
