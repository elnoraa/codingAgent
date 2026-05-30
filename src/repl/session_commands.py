"""Session management commands — /save, /load, /sessions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from src.formatting import bold, cyan, dim, green, red

if TYPE_CHECKING:
    from src.repl.repl import Repl

logger = logging.getLogger(__name__)


def handle_session_save(repl: Repl, parts: list[str]) -> None:
    """Save the current session."""
    from src.session import save_session

    if len(parts) < 2:
        print(f"  {dim('Usage: /save <name>')}")
        return
    name = parts[1].strip()
    if not name:
        print(f"  {dim('Usage: /save <name>')}")
        return

    result = save_session(
        name=name,
        messages=repl.messages,
        mode=repl.mode,
        working_directory=repl.working_directory,
        model=repl.llm.model,
    )
    if result.startswith("Error:"):
        logger.warning("Session save failed: %s", result)
        print(f"  {red('✗')} {result}")
    else:
        logger.info("Session saved: %s -> %s", name, result)
        print(f"  {green('✓')} {dim('Session saved to')} {cyan(result)}")


def handle_session_load(repl: Repl, parts: list[str]) -> None:
    """Load a saved session."""
    from src.session import load_session

    if len(parts) < 2:
        print(f"  {dim('Usage: /load <name>')}")
        return
    name = parts[1].strip()
    if not name:
        print(f"  {dim('Usage: /load <name>')}")
        return

    session = load_session(name, repl.working_directory)
    if session is None:
        print(f"  {red('✗')} {dim('Session not found:')} {cyan(name)}")
        print(f"  {dim('Use /sessions to list available sessions.')}")
        return

    loaded_msgs = session.get("messages", [])
    if isinstance(loaded_msgs, list):
        repl.messages = cast("list[dict[str, object]]", loaded_msgs)
    loaded_mode = session.get("mode", "code")
    if isinstance(loaded_mode, str):
        repl.mode = loaded_mode

    msg_count = len(repl.messages)
    logger.info("Session loaded: %s (%d messages, %s mode)", name, msg_count, loaded_mode)
    print(f"  {green('✓')} {dim('Loaded session:')} {cyan(name)} {dim(f'({msg_count} messages, {loaded_mode} mode)')}")


def handle_session_list(repl: Repl) -> None:
    """List all saved sessions."""
    from src.session import list_sessions

    sessions = list_sessions(repl.working_directory)
    if not sessions:
        print(f"  {dim('No saved sessions found.')}")
        print(f"  {dim('Use /save <name> to save the current session.')}")
        return

    print(f"  {bold('Saved Sessions')}")
    print()
    for s in sessions:
        name = cast("str", s.get("name", "?"))
        saved_at = cast("str", s.get("saved_at", "?"))
        mode = cast("str", s.get("mode", "?"))
        msg_count = cast("int", s.get("message_count", 0))
        # Truncate ISO timestamp for display
        display_time = saved_at[:19] if len(saved_at) > 19 else saved_at
        print(f"  {cyan(name.rjust(20))}  {dim(display_time)}  {dim(f'({msg_count} msgs, {mode})')}")


def handle_persona(repl: Repl, parts: list[str]) -> None:
    """Set or clear the custom persona."""
    if len(parts) < 2:
        print(f"  {dim('Usage: /persona <text>')}")
        print(f"  {dim('       /persona clear')}")
        return

    text = parts[1].strip()
    if text.lower() == "clear":
        if repl._custom_persona:
            repl._custom_persona = ""
            print(f"  {green('✓')} {dim('Custom persona cleared.')}")
        else:
            print(f"  {dim('No custom persona to clear.')}")
        return

    if not text:
        print(f"  {dim('Usage: /persona <text>')}")
        return

    repl._custom_persona = text
    logger.info("Custom persona set (length=%d)", len(text))
    print(f"  {green('✓')} {dim('Custom persona set. It will be appended to the system prompt for all future turns.')}")
