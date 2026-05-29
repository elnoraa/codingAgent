"""Docker integration for managing containers and images."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)


def _run_docker(cmd: list[str], ctx: ToolContext, timeout: int = 60) -> tuple[int, str, str]:
    """Run a docker command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["docker"] + cmd,
            capture_output=True, text=True, cwd=ctx.working_directory,
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

    if action == "ps":
        # List containers
        all_flag = ["--all"] if args.get("all") else []
        ret, stdout, stderr = _run_docker(
            ["ps", "--format", "{{json .}}"] + all_flag, ctx,
        )
        if ret != 0:
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
            ["images", "--format", "{{json .}}"], ctx,
        )
        if ret != 0:
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

        cmd = ["build"]
        if tag:
            cmd.extend(["-t", tag])
        if dockerfile:
            cmd.extend(["-f", dockerfile])
        cmd.append(path)

        ret, stdout, stderr = _run_docker(cmd, ctx, timeout=300)
        if ret != 0:
            return f"Build failed:\n{stderr}"
        return f"Build succeeded:\n{stdout[:2000]}"

    elif action == "up":
        # docker compose up
        services = args.get("services", "")
        detached = args.get("detach", True)
        file = args.get("file", "")

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

        ret, stdout, stderr = _run_docker(
            ["exec", container] + command.split(), ctx, timeout=30,
        )
        if ret != 0:
            return f"Command failed (exit {ret}):\n{stderr}"
        return stdout or "(no output)"

    elif action == "compose":
        # docker compose ps
        file = args.get("file", "")
        cmd = ["compose", "ps"]
        if file:
            cmd.extend(["-f", file])

        ret, stdout, stderr = _run_docker(cmd, ctx)
        if ret != 0:
            return f"Error:\n{stderr}"
        return stdout or "No compose services running."

    else:
        return (
            f"Unknown action: {action}\n"
            f"Available actions: ps, images, build, up, down, logs, exec, compose"
        )


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
)
