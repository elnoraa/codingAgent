"""Mermaid diagram rendering for the Coding Agent.

Detects ```mermaid code blocks in LLM responses and provides
rendering via mermaid.ink URL (for browser viewing) or ASCII art fallback.
"""

from __future__ import annotations

import re
import webbrowser
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

# Regex to detect mermaid code blocks
MERMAID_BLOCK_RE = re.compile(
    r"```mermaid\n(.*?)```",
    re.DOTALL,
)

# Base URL for mermaid.ink rendering
MERMAID_INK_URL = "https://mermaid.ink/img/"


def extract_mermaid_blocks(text: str) -> list[dict[str, Any]]:
    """Extract all mermaid code blocks from text.

    Returns a list of dicts with 'code' (the mermaid source) and 'position'
    (start/end indices in the original text).
    """
    blocks: list[dict[str, Any]] = []
    for match in MERMAID_BLOCK_RE.finditer(text):
        blocks.append(
            {
                "code": match.group(1).strip(),
                "start": match.start(),
                "end": match.end(),
            }
        )
    return blocks


def get_mermaid_url(code: str) -> str:
    """Generate a mermaid.ink URL for viewing a mermaid diagram.

    The code is base64-encoded and passed as a query parameter.
    """
    import base64
    import urllib.parse

    # Mermaid.ink expects the diagram source as a base64-encoded parameter
    encoded = base64.urlsafe_b64encode(code.encode("utf-8")).decode("ascii")
    return f"{MERMAID_INK_URL}{urllib.parse.quote(encoded)}"


def open_diagram_in_browser(code: str) -> bool:
    """Open a mermaid diagram in the default browser."""
    url = get_mermaid_url(code)
    try:
        webbrowser.open(url)
        return True
    except Exception as e:
        logger.debug("Failed to open browser: %s", e)
        return False


def render_diagram_ascii(code: str) -> str:
    """Render a simple mermaid diagram as ASCII art (fallback).

    This is a basic heuristic renderer for common diagram types.
    For complex diagrams, recommend opening in browser.
    """
    lines = code.split("\n")
    result: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect common mermaid patterns and render basic ASCII
        if "graph" in line.lower() or "flowchart" in line.lower():
            result.append("─" * 40)
            result.append("  FLOWCHART DIAGRAM")
            result.append("─" * 40)

        elif "-->" in line:
            # Arrow connection: A --> B
            parts = line.split("-->")
            result.append(f"  [{parts[0].strip()}] ──▶ [{parts[1].strip()}]")

        elif "---" in line:
            parts = line.split("---")
            result.append(f"  [{parts[0].strip()}] ─── [{parts[1].strip()}]")

        elif "=>" in line:
            parts = line.split("=>")
            result.append(f"  [{parts[0].strip()}] ══▶ [{parts[1].strip()}]")

        elif "classdef" in line.lower():
            continue  # Skip class definitions in ASCII rendering

        else:
            result.append(f"  {line}")

    return "\n".join(result)


def process_mermaid_blocks(text: str, open_browser: bool = False) -> str:
    """Process mermaid blocks in text, rendering them appropriately.

    Args:
        text: The response text containing potential mermaid blocks
        open_browser: If True, open diagrams in browser

    Returns:
        Text with mermaid blocks replaced by rendered versions
    """
    from .utils import cyan, dim

    blocks = extract_mermaid_blocks(text)
    if not blocks:
        return text

    for block in blocks:
        code = block["code"]

        # Try to render as ASCII
        ascii_render = render_diagram_ascii(code)

        # Generate URL for browser viewing
        url = get_mermaid_url(code)

        # Create replacement text
        replacement = (
            f"\n{dim('┌─ Mermaid Diagram ' + '─' * 40)}\n"
            f"  {dim('URL:')} {cyan(url)}\n"
            f"{ascii_render}\n"
            f"{dim('└' + '─' * 60)}\n"
        )

        # Optionally open in browser
        if open_browser:
            open_diagram_in_browser(code)

        # Replace the original mermaid block
        text = text[: block["start"]] + replacement + text[block["end"] :]

    return text
