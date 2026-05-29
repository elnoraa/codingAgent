from __future__ import annotations

import logging
import subprocess
from typing import Any

from tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    url = args.get("url")
    max_length = int(args.get("maxLength", 10000))
    timeout = int(args.get("timeout", 15))
    logger.info("execute: url=%s, maxLength=%d, timeout=%d", url, max_length, timeout)
    if not url:
        return 'Error: missing required argument "url".'

    # SSRF protection: block private/internal IPs
    try:
        from src.utils import validate_url_target
        ssrf_error = validate_url_target(url)
        if ssrf_error:
            return ssrf_error
    except ImportError:
        pass

    # Use curl to fetch the URL
    try:
        result = subprocess.run(
            ["curl", "-sSL", "-m", str(timeout), url],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
    except FileNotFoundError:
        # Curl not available, try wget
        try:
            result = subprocess.run(
                ["wget", "-q", "-O", "-", "--timeout=" + str(timeout), url],
                capture_output=True,
                text=True,
                timeout=timeout + 5,
            )
        except FileNotFoundError:
            return "[Error] Neither curl nor wget is installed on this system"
        except subprocess.TimeoutExpired:
            return "[Error] Request timed out"
        except Exception as exc:
            return f"[Error] {exc}"
    except subprocess.TimeoutExpired:
        return "[Error] Request timed out"
    except Exception as exc:
        return f"[Error] {exc}"

    if result.returncode != 0:
        error_msg = result.stderr.strip() or f"curl exited with code {result.returncode}"
        return f"[Error] Failed to fetch URL: {error_msg}"

    content = result.stdout.strip()

    # Try to get content type
    content_type = ""
    for line in result.stderr.split("\n"):
        if "Content-Type:" in line:
            content_type = line.split(":", 1)[1].strip()
            break

    # Truncate if too long
    if len(content) > max_length:
        content = content[:max_length]
        content += f"\n\n... (truncated, full response was {len(result.stdout.strip())} bytes)"

    header = f"URL: {url}"
    if content_type:
        header += f" | Content-Type: {content_type}"
    header += f" | {len(result.stdout.strip())} bytes"

    return header + "\n\n" + content


url_fetch_tool = Tool(
    name="url_fetch",
    description=(
        "Fetch a URL and return its text content. Useful for reading documentation, "
        "API responses, or web pages. Uses curl (or wget as fallback). "
        "Truncates long responses."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch (http:// or https://)",
            },
            "maxLength": {
                "type": "number",
                "description": "Maximum characters to return (default: 10000)",
            },
            "timeout": {
                "type": "number",
                "description": "Request timeout in seconds (default: 15)",
            },
        },
        "required": ["url"],
    },
    execute=execute,
    read_only=True,
)
