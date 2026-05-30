"""Tool: url_fetch — fetch URL content using Python's built-in urllib.

Uses stdlib only (DIP compliance — no dependency on external binaries like curl/wget).
Keeps URLs within process memory (M5 — prevents URL leakage via /proc).
Applies SSRF protection (reuses validate_url_target from security.py, DRY).
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    url = args.get("url")
    max_length = int(args.get("maxLength", 10000))
    timeout = int(args.get("timeout", 15))
    logger.info("execute: url=%s, maxLength=%d, timeout=%d", url, max_length, timeout)
    if not url:
        return 'Error: missing required argument "url".'

    # Validate URL length
    from src.utils import MAX_URL_LENGTH, validate_length

    error = validate_length(url, MAX_URL_LENGTH, "URL")
    if error:
        return error

    # SSRF protection: block private/internal IPs (DRY: reuse from security.py)
    from src.security import validate_url_target

    ssrf_error = validate_url_target(url)
    if ssrf_error:
        return ssrf_error

    # Fetch using urllib.request (stdlib) instead of curl/wget subprocess (M5)
    # This keeps the URL within process memory, preventing leakage via /proc
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CodingAgent/1.0"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            content_type = response.headers.get("Content-Type", "")
            content_bytes = response.read()
            content = content_bytes.decode("utf-8", errors="replace")
            content_length = len(content)
    except urllib.error.HTTPError as exc:
        return f"[Error] HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return f"[Error] Failed to fetch URL: {exc.reason}"
    except ValueError as exc:
        return f"[Error] Invalid URL: {exc}"
    except OSError as exc:
        return f"[Error] Connection failed: {exc}"
    except Exception as exc:
        return f"[Error] {exc}"

    # Truncate if too long
    truncated = False
    if len(content) > max_length:
        content = content[:max_length]
        truncated = True

    header = f"URL: {url}"
    if content_type:
        header += f" | Content-Type: {content_type}"
    header += f" | {content_length} bytes"
    if truncated:
        header += f" (showing {max_length} chars)"

    return header + "\n\n" + content


url_fetch_tool = Tool(
    name="url_fetch",
    description=(
        "Fetch a URL and return its text content. Useful for reading documentation, "
        "API responses, or web pages. Uses urllib (stdlib). "
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
