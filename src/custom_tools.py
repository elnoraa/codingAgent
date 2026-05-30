"""Custom Tools via Config for the Coding Agent.

Allows users to define custom tools through a JSON config file
without writing Python code. Supports handler types: bash, http, python.

**Security considerations:**
- Bash and Python handlers run with the same restrictions as their built-in
  counterparts (write-path enforcement, command scanning, restricted imports).
- HTTP handlers have SSRF protection (private IPs are blocked).
- A warning is logged whenever bash or python type tools are loaded.
- Template substitution values are validated to prevent shell metacharacter
  injection in bash tools and CR/LF injection in HTTP tools.
"""

from __future__ import annotations

import json
import os
import re as _re
import subprocess
from dataclasses import dataclass, field
from typing import Any

from src.tools import Tool, ToolContext

from .logging_config import get_logger

logger = get_logger(__name__)

# Characters that have special meaning in shell and should be blocked
# in template substitutions for bash-type custom tools
_SHELL_DANGEROUS_PATTERN = _re.compile(r"[;&|`$(){}]")

logger = get_logger(__name__)


@dataclass
class CustomToolDef:
    """Definition of a custom tool from config."""

    name: str
    description: str
    input_schema: dict[str, object]
    handler_type: str  # "bash", "http", "python"
    handler_config: dict[str, Any] = field(default_factory=dict)


def _validate_template_value(value: str, handler_type: str) -> str | None:
    """Validate a template substitution value for safety.

    For bash-type handlers, blocks shell metacharacters.
    For http-type handlers, blocks CR/LF injection.

    Returns an error message if the value is unsafe, ``None`` if safe.
    """
    if not isinstance(value, str):
        return None

    if handler_type == "bash":
        if _SHELL_DANGEROUS_PATTERN.search(value):
            return f"Error: Template substitution value contains shell metacharacters that are not allowed: {value!r}"
        if value.startswith("-"):
            return (
                f"Error: Template substitution value starts with '-' which could "
                f"be interpreted as a command-line flag: {value!r}"
            )

    elif handler_type == "http":
        if "\r" in value or "\n" in value:
            return (
                f"Error: Template substitution value contains CR/LF characters "
                f"which could enable HTTP header injection: {value!r}"
            )

    return None


def _handle_bash_tool(args: dict[str, object], ctx: ToolContext, defn: CustomToolDef) -> str:
    """Execute a bash command with template substitution.

    Applies the same command-scanner checks as the built-in ``bash`` tool
    to prevent writes outside the working directory.
    """
    # Log a warning each time a custom bash tool is called
    logger.warning(
        "Custom bash tool '%s' is executing a shell command. "
        "This tool was defined in a config file and executes arbitrary commands. "
        "Only proceed if you trust the config file.",
        defn.name,
    )

    command_template = defn.handler_config.get("command", "")
    if not command_template:
        return "Error: No command specified in tool definition."

    # Template substitution: {{param_name}} -> args["param_name"]
    try:
        command = command_template
        for key, value in args.items():
            # Validate the substitution value for shell safety
            error = _validate_template_value(str(value), "bash")
            if error:
                return error
            command = command.replace("{{" + key + "}}", str(value))
    except Exception as e:
        return f"Error in template substitution: {e}"

    # Apply the same command scanner as the built-in bash tool
    try:
        from src.tools.bash_tool import _check_command_for_outside_writes
    except ImportError:
        pass
    else:
        scanner_error = _check_command_for_outside_writes(command, ctx.working_directory)
        if scanner_error:
            return scanner_error

    # Validate workdir if specified in handler config
    workdir = defn.handler_config.get("workdir") or ctx.working_directory
    error = ctx.validate_write_path(workdir)
    if error:
        return error

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=workdir,
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
    """Make an HTTP request with SSRF protection."""
    url_template = defn.handler_config.get("url", "")
    method = defn.handler_config.get("method", "GET").upper()
    if not url_template:
        return "Error: No URL specified in tool definition."

    # Template substitution for URL
    try:
        url = url_template
        for key, value in args.items():
            # Validate the substitution value for HTTP safety
            error = _validate_template_value(str(value), "http")
            if error:
                return error
            url = url.replace("{{" + key + "}}", str(value))
    except Exception as e:
        return f"Error in URL template substitution: {e}"

    # SSRF protection: block requests to private/internal IPs
    try:
        from src.utils import validate_url_target

        error = validate_url_target(url)
        if error:
            return error
    except ImportError:
        pass

    try:
        import urllib.error
        import urllib.parse
        import urllib.request

        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            return f"HTTP {response.status}:\n{body[:2000]}"
    except Exception as e:
        return f"HTTP Error: {e}"


def _handle_python_tool(args: dict[str, object], ctx: ToolContext, defn: CustomToolDef) -> str:
    """Execute embedded Python script with args as variables.

    Uses the same restricted execution environment as the built-in
    ``python`` tool (blocked dangerous imports, write-path enforcement).
    """
    # Log a warning each time a custom python tool is called
    logger.warning(
        "Custom python tool '%s' is executing arbitrary Python code. "
        "This tool was defined in a config file. "
        "Only proceed if you trust the config file.",
        defn.name,
    )

    script = defn.handler_config.get("script", "")
    if not script:
        return "Error: No script specified in tool definition."

    # Use the restricted Python REPL if working directory is set
    if ctx.working_directory:
        try:
            from src.python_repl import PythonRepl

            repl = PythonRepl(restrict_to_working_directory=ctx.working_directory)
            # Prepend args as variable assignments so the script can use them
            preamble = "\n".join(f"{k} = {v!r}" for k, v in args.items())
            full_code = preamble + "\n" + script if preamble else script
            return repl.execute(full_code)
        except Exception as e:
            return f"Error executing script: {e}"

    # Fallback: unrestricted execution (no working directory set)
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
        with open(config_path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to load custom tools config: %s", e)
        return []

    # ── Integrity check (session-modified file detection) ──────────────
    from src.tools import was_file_modified_during_session

    if was_file_modified_during_session(config_path):
        logger.warning(
            "Custom tools config '%s' was modified during the current "
            "session. This could indicate a configuration injection attack.",
            config_path,
        )
        print()
        print("  ⚠  **SECURITY WARNING**")
        print(f"     Custom tools config '{config_path}' has been modified")
        print("     during this session. This file was written or modified")
        print("     by the AI agent.")
        print("     Proceeding could execute arbitrary commands.")
        print()
        response = input("  Load anyway? Only say 'yes' if you wrote this file yourself. [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            logger.info("Custom tools loading denied — config was session-modified")
            print("  Custom tools not loaded (declined security warning).")
            return []
        print()

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

            # Log a security warning for potentially dangerous handler types
            if handler_type in ("bash", "python"):
                logger.warning(
                    "Loading custom tool '%s' with type '%s' — this tool can "
                    "execute arbitrary %s commands. Ensure the config file is "
                    "trustworthy.",
                    name,
                    handler_type,
                    "shell" if handler_type == "bash" else "Python",
                )

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
