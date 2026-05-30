"""Docker integration for managing containers and images.

Security: Applies write-path validation, data exfiltration scanning, and
command substitution checks (reusing the same scanners from bash_tool.py
per DRY principles). Paths accepted by build/up/down actions are validated
against the working directory.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def _check_docker_path(path: str, ctx: ToolContext) -> str | None:
    """Validate a path parameter is within the working directory.

    Reuses ctx.validate_write_path() — DRY: don't write a second path validator.
    """
    if not path:
        return None
    return ctx.validate_write_path(path)


def _check_docker_command_for_security(command: str, ctx: ToolContext) -> str | None:
    """Check a Docker exec command for security violations.

    Reuses the bash tool's command scanner and exfiltration detection (DRY).
    """
    # Import the command scanner from bash_tool (DRY: reuse, don't rewrite)
    try:
        from src.tools.bash_tool import _check_command_for_outside_writes
    except ImportError:
        pass
    else:
        scanner_error = _check_command_for_outside_writes(command, ctx.working_directory)
        if scanner_error:
            return scanner_error

    # Check for sensitive environment variable access
    from src.exfiltration_detection import _EXFIL_NETWORK_COMMANDS, _EXFIL_SENSITIVE_FILES

    command_lower = command.lower()
    for sensitive_file in _EXFIL_SENSITIVE_FILES:
        if sensitive_file in command_lower:
            parts = sensitive_file.split("/")
            if any(part in command_lower for part in parts):
                logger.warning(
                    "Docker exec blocked: command references sensitive file '%s'",
                    sensitive_file,
                )
                return (
                    f"Error: Docker exec command references sensitive file "
                    f"'{sensitive_file}'. This is blocked for security."
                )

    for net_cmd in _EXFIL_NETWORK_COMMANDS:
        if net_cmd in command_lower:
            logger.warning(
                "Docker exec blocked: command uses network tool '%s'",
                net_cmd,
            )
            return (
                f"Error: Docker exec command uses network tool '{net_cmd}'. "
                f"This could be used for data exfiltration and is blocked."
            )

    return None


def _run_docker(cmd: list[str], ctx: ToolContext, timeout: int = 60) -> tuple[int, str, str]:
    """Run a docker command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(  # noqa: S603
            ["docker"] + cmd,
            capture_output=True,
            text=True,
            cwd=ctx.working_directory,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "Error: docker not found. Is Docker installed?"
    except subprocess.TimeoutExpired:
        return -1, "", f"Error: docker command timed out ({timeout}s)"
    except Exception as e:
        return -1, "", f"Error: {e}"


def _format_container(container: dict[str, Any]) -> str:
    """Format a single container for display."""
    status = container.get("Status", "")
    state = container.get("State", "")
    name = container.get("Names", [""])[0] if container.get("Names") else ""
    ports = container.get("Ports", "")
    image = container.get("Image", "")

    # Color by state
    if "running" in (state or status).lower():
        state_str = "● running"
    elif "exited" in (state or status).lower():
        state_str = "○ exited"
    elif "paused" in (state or status).lower():
        state_str = "⏸ paused"
    else:
        state_str = state or status

    port_str = ""
    if ports:
        # Parse port mappings (simplified)
        port_mappings = ports.split(", ")
        port_str = f" → {' '.join(port_mappings)}"

    return f"  {name:<25} {state_str:<12} {image:<20}{port_str}"


def _format_image(image: dict[str, Any]) -> str:
    """Format a single image for display."""
    repo = image.get("Repository", "<none>")
    tag = image.get("Tag", "<none>")
    img_id = image.get("ID", "")[:12]
    created = image.get("CreatedAt", "")
    size = image.get("Size", "")
    return f"  {repo:<25} {tag:<15} {img_id:<12} {created:<20} {size}"


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    """Execute a Docker action."""
    action = args.get("action", "ps").lower()
    logger.info("execute: action=%s", action)

    if action == "ps":
        # List containers
        all_flag = ["--all"] if args.get("all") else []
        ret, stdout, stderr = _run_docker(
            ["ps", "--format", "{{json .}}"] + all_flag,
            ctx,
        )
        if ret != 0:
            logger.warning("Docker ps failed: %s", stderr[:200])
            return f"Error: {stderr}"

        lines = stdout.split("\n")
        if not lines or lines == [""]:
            return "No containers found."

        result = ["\n  CONTAINER              STATUS         IMAGE                  PORTS"]
        result.append("  " + "─" * 70)
        for line in lines:
            if line.strip():
                try:
                    container = json.loads(line)
                    result.append(_format_container(container))
                except json.JSONDecodeError:
                    result.append(f"  {line}")
        return "\n".join(result)

    elif action == "images":
        ret, stdout, stderr = _run_docker(
            ["images", "--format", "{{json .}}"],
            ctx,
        )
        if ret != 0:
            logger.warning("Docker images failed: %s", stderr[:200])
            return f"Error: {stderr}"

        lines = stdout.split("\n")
        if not lines or lines == [""]:
            return "No images found."

        result = ["\n  REPOSITORY               TAG              IMAGE ID      CREATED              SIZE"]
        result.append("  " + "─" * 80)
        for line in lines:
            if line.strip():
                try:
                    image = json.loads(line)
                    result.append(_format_image(image))
                except json.JSONDecodeError:
                    result.append(f"  {line}")
        return "\n".join(result)

    elif action == "build":
        # docker build
        path = args.get("path", ".")
        tag = args.get("tag", "")
        dockerfile = args.get("dockerfile", "")

        logger.info("Docker build: path=%s, tag=%s, dockerfile=%s", path, tag, dockerfile)

        # Validate paths within working directory (SRP: security is separated from logic)
        path_error = _check_docker_path(path, ctx)
        if path_error:
            return path_error
        if dockerfile:
            df_error = _check_docker_path(dockerfile, ctx)
            if df_error:
                return df_error

        logger.info("Docker build: path=%s, tag=%s, dockerfile=%s", path, tag, dockerfile)

        cmd = ["build"]
        if tag:
            cmd.extend(["-t", tag])
        if dockerfile:
            cmd.extend(["-f", dockerfile])
        cmd.append(path)

        ret, stdout, stderr = _run_docker(cmd, ctx, timeout=300)
        if ret != 0:
            logger.warning("Docker build failed: %s", stderr[:200])
            return f"Build failed:\n{stderr}"
        logger.info("Docker build succeeded")
        return f"Build succeeded:\n{stdout[:2000]}"

    elif action == "up":
        # docker compose up
        services = args.get("services", "")
        detached = args.get("detach", True)
        file = args.get("file", "")

        # Validate compose file path (M8: path validation)
        if file:
            file_error = _check_docker_path(file, ctx)
            if file_error:
                return file_error

        cmd = ["compose", "up"]
        if detached:
            cmd.append("-d")
        if file:
            cmd.extend(["-f", file])
        if services:
            cmd.extend(services.split())

        ret, stdout, stderr = _run_docker(cmd, ctx, timeout=120)
        if ret != 0:
            return f"Compose up failed:\n{stderr}"
        return f"Services started:\n{stdout[:1000]}"

    elif action == "down":
        # docker compose down
        file = args.get("file", "")
        volumes = args.get("volumes", False)

        # Validate compose file path (M8)
        if file:
            file_error = _check_docker_path(file, ctx)
            if file_error:
                return file_error

        cmd = ["compose", "down"]
        if volumes:
            cmd.append("-v")
        if file:
            cmd.extend(["-f", file])

        ret, stdout, stderr = _run_docker(cmd, ctx, timeout=60)
        if ret != 0:
            return f"Compose down failed:\n{stderr}"
        return "Services stopped and removed."

    elif action == "logs":
        # docker logs
        name_or_id = args.get("container", "")
        if not name_or_id:
            return "Error: 'container' parameter required for logs action"

        follow = args.get("follow", False)
        tail = args.get("tail", 50)

        cmd = ["logs", "--tail", str(tail)]
        if follow:
            cmd.append("--follow")
        cmd.append(name_or_id)

        ret, stdout, stderr = _run_docker(cmd, ctx, timeout=30)
        if ret != 0:
            return f"Error fetching logs:\n{stderr}"
        return stdout or "(empty log)"

    elif action == "exec":
        # docker exec
        container = args.get("container", "")
        command = args.get("command", "")
        if not container or not command:
            return "Error: 'container' and 'command' parameters required"

        # Security: scan the command before executing (H1)
        logger.warning("Docker exec action requested — executing command inside container %s", container)
        security_error = _check_docker_command_for_security(command, ctx)
        if security_error:
            return security_error

        # Use shlex.split() for proper quoted-argument handling (M6 — LSP compliance)
        import shlex

        try:
            split_command = shlex.split(command)
        except ValueError as exc:
            # shlex.split can raise ValueError on unbalanced quotes
            return f"Error: Invalid command syntax — {exc}"

        ret, stdout, stderr = _run_docker(
            ["exec", container] + split_command,
            ctx,
            timeout=30,
        )
        if ret != 0:
            return f"Command failed (exit {ret}):\n{stderr}"
        return stdout or "(no output)"

    elif action == "compose":
        # docker compose ps
        file = args.get("file", "")

        # Validate compose file path (M8)
        if file:
            file_error = _check_docker_path(file, ctx)
            if file_error:
                return file_error

        cmd = ["compose", "ps"]
        if file:
            cmd.extend(["-f", file])

        ret, stdout, stderr = _run_docker(cmd, ctx)
        if ret != 0:
            return f"Error:\n{stderr}"
        return stdout or "No compose services running."

    else:
        return f"Unknown action: {action}\nAvailable actions: ps, images, build, up, down, logs, exec, compose"


docker_tool = Tool(
    name="docker",
    description=(
        "Manage Docker containers, images, and Compose services. "
        "Actions: ps (list containers), images (list images), build (build image), "
        "up (compose up), down (compose down), logs (container logs), "
        "exec (run command in container), compose (show compose status)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Docker action to perform",
                "enum": ["ps", "images", "build", "up", "down", "logs", "exec", "compose"],
            },
            "all": {
                "type": "boolean",
                "description": "Include stopped containers (for ps action)",
            },
            "path": {
                "type": "string",
                "description": "Build context path (for build action)",
            },
            "tag": {
                "type": "string",
                "description": "Image tag (for build action)",
            },
            "dockerfile": {
                "type": "string",
                "description": "Dockerfile path (for build action)",
            },
            "services": {
                "type": "string",
                "description": "Space-separated service names (for up action)",
            },
            "detach": {
                "type": "boolean",
                "description": "Run containers in background (for up, default: true)",
            },
            "file": {
                "type": "string",
                "description": "Compose file path",
            },
            "volumes": {
                "type": "boolean",
                "description": "Remove volumes (for down action)",
            },
            "container": {
                "type": "string",
                "description": "Container name/ID (for logs, exec actions)",
            },
            "command": {
                "type": "string",
                "description": "Command to execute (for exec action)",
            },
            "follow": {
                "type": "boolean",
                "description": "Follow log output (for logs action)",
            },
            "tail": {
                "type": "number",
                "description": "Number of recent log lines (for logs, default: 50)",
            },
        },
        "required": ["action"],
    },
    execute=execute,
    read_only=False,
)
