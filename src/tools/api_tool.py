"""API endpoint tester for making HTTP requests during development."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any
from urllib.parse import urlparse

from src.tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)

# Saved request profiles (in-memory cache)
_saved_requests: dict[str, dict[str, Any]] = {}


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    method = (args.get("method", "GET")).upper()
    url = args.get("url", "")
    headers = args.get("headers", {})
    body = args.get("body")
    timeout = int(args.get("timeout", 10))
    save_as = args.get("save_as")
    profile = args.get("profile")

    if not url:
        return 'Error: missing required argument "url".'

    # Handle saved profiles
    if profile:
        if profile in _saved_requests:
            saved = _saved_requests[profile]
            method = saved.get("method", method)
            url = saved.get("url", url)
            headers = saved.get("headers", headers)
            body = saved.get("body", body)
        else:
            return f"Error: profile '{profile}' not found."

    # Validate URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        # Assume localhost if no scheme
        url = f"http://localhost:{url}" if url.isdigit() else f"http://{url}"

    # SSRF protection: block requests to private/internal IPs
    try:
        from src.utils import validate_url_target
        ssrf_error = validate_url_target(url)
        if ssrf_error:
            return ssrf_error
    except ImportError:
        pass

    # Build request
    try:
        data = None
        if body:
            data = body.encode("utf-8")
            if "Content-Type" not in {k.lower(): v for k, v in headers.items()}:
                headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )

        # Execute
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            status_code = response.status
            response_headers = dict(response.headers)

        elapsed = time.time() - start_time

        # Format response
        result_parts: list[str] = []
        result_parts.append(f"● {method} {url}")
        result_parts.append(f"  Status: {status_code}")
        result_parts.append(f"  Time: {elapsed:.2f}s")

        # Show response headers (summary)
        result_parts.append(f"  Headers:")
        for key in ["content-type", "content-length", "server"]:
            if key in response_headers:
                result_parts.append(f"    {key}: {response_headers[key]}")

        # Show response body (truncated)
        result_parts.append(f"  Body:")
        try:
            parsed_body = json.loads(response_body)
            body_str = json.dumps(parsed_body, indent=2)
        except (json.JSONDecodeError, ValueError):
            body_str = response_body

        if len(body_str) > 2000:
            body_str = body_str[:2000] + f"\n... (truncated, full: {len(response_body)} chars)"

        result_parts.append(body_str)

        # Save profile if requested
        if save_as:
            _saved_requests[save_as] = {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
            }
            result_parts.append(f"\nProfile saved as: {save_as}")

        return "\n".join(result_parts)

    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500]
        return (
            f"● {method} {url}\n"
            f"  Status: {e.code}\n"
            f"  Body: {body_text}\n"
            f"(HTTP error)"
        )

    except urllib.error.URLError as e:
        return f"✗ Connection failed: {e.reason}"

    except Exception as e:
        return f"✗ Error: {e}"


# Tool definition
api_tool = Tool(
    name="api",
    description=(
        "Make HTTP requests to API endpoints. Supports GET, POST, PUT, DELETE, PATCH. "
        "Can save and reuse request profiles. Use for testing local dev servers."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP method: GET, POST, PUT, DELETE, PATCH (default: GET)",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
            },
            "url": {
                "type": "string",
                "description": "Request URL (e.g., http://localhost:8000/api/users). "
                               "Auto-prefixes http:// if no scheme given.",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs",
            },
            "body": {
                "type": "string",
                "description": "Request body (for POST/PUT/PATCH). JSON strings auto-detect Content-Type.",
            },
            "timeout": {
                "type": "number",
                "description": "Request timeout in seconds (default: 10)",
            },
            "save_as": {
                "type": "string",
                "description": "Save this request as a named profile for reuse",
            },
            "profile": {
                "type": "string",
                "description": "Load a saved request profile",
            },
        },
        "required": ["url"],
    },
    execute=execute,
    read_only=False,
)
