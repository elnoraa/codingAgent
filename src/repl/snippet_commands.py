"""Snippet management commands — /snippet."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.formatting import bold, green, red
from src.repl.ui import format_size

if TYPE_CHECKING:
    from src.repl.repl import Repl


def _get_last_assistant_response(repl: Repl) -> str:
    """Get the last assistant text response."""
    for msg in reversed(repl.messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
    return ""


def handle_snippet(repl: Repl, args: str) -> None:
    """Handle /snippet commands."""
    from src.snippets import delete_snippet, list_snippets, load_snippet, save_snippet

    parts = args.strip().split(maxsplit=1)
    subcommand = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if subcommand == "list":
        snippets = list_snippets()
        if not snippets:
            print("  No snippets saved.")
            return
        print(f"\n  {bold('Saved Snippets')}")
        for s in snippets:
            desc = f" — {s['description']}" if s["description"] else ""
            size_str = format_size(s["size"])
            print(f"  {green(s['name'])}{desc} ({size_str})")

    elif subcommand == "save":
        if not rest:
            print("  Usage: /snippet save <name>")
            return
        # Save the last assistant response as a snippet
        last_response = _get_last_assistant_response(repl)
        if not last_response:
            print("  No assistant response to save.")
            return
        if save_snippet(rest, last_response):
            print(f"  {green('✓')} Saved snippet: {rest}")

    elif subcommand == "load":
        if not rest:
            print("  Usage: /snippet load <name>")
            return
        content = load_snippet(rest)
        if content is None:
            print(f"  {red('✗')} Snippet not found: {rest}")
            return
        print(f"\n  {bold(f'Snippet: {rest}')}")
        print(content)

    elif subcommand == "delete":
        if not rest:
            print("  Usage: /snippet delete <name>")
            return
        if delete_snippet(rest):
            print(f"  {green('✓')} Deleted snippet: {rest}")
        else:
            print(f"  {red('✗')} Snippet not found: {rest}")

    elif subcommand == "apply":
        if not rest:
            print("  Usage: /snippet apply <name>")
            return
        content = load_snippet(rest)
        if content is None:
            print(f"  {red('✗')} Snippet not found: {rest}")
            return
        # Insert snippet into user input buffer (next message)
        repl._pending_input = content
        print(f"  {green('✓')} Loaded snippet '{rest}' — press Enter to send")

    else:
        print("  Usage: /snippet [list|save|load|delete|apply] <name>")
