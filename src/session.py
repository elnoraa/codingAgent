"""Session save/load functionality for the Coding Agent.

Sessions are stored as JSON files in the working_directory/sessions/ folder.
Each session captures: messages, mode, working_directory, model, timestamp.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import cast

from .logging_config import get_logger

logger = get_logger(__name__)

SESSION_DIR = "sessions"


def _sessions_dir(working_directory: str) -> str:
    return os.path.join(working_directory, SESSION_DIR)


def save_session(
    name: str,
    messages: list[dict[str, object]],
    mode: str,
    working_directory: str,
    model: str,
    is_autosave: bool = False,
) -> str:
    """Save the current session to a JSON file. Returns the file path."""
    s_dir = _sessions_dir(working_directory)
    Path(s_dir).mkdir(parents=True, exist_ok=True)

    safe_name = name.strip().replace(" ", "-")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_.")
    if not safe_name:
        return "Error: invalid session name. Use alphanumeric characters, dashes, or underscores."

    filepath = os.path.join(s_dir, f"{safe_name}.json")

    session_data = {
        "name": safe_name,
        "saved_at": datetime.now().isoformat(),
        "mode": mode,
        "working_directory": working_directory,
        "model": model,
        "messages": messages,
        "is_autosave": is_autosave,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)

    logger.info("Session saved: name=%s, mode=%s, messages=%d, file=%s", safe_name, mode, len(messages), filepath)
    return filepath


def load_session(name: str, working_directory: str) -> dict[str, object] | None:
    """Load a session by name. Returns the session dict or None if not found."""
    s_dir = _sessions_dir(working_directory)
    safe_name = name.strip().replace(" ", "-")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_.")
    if not safe_name:
        return None

    filepath = os.path.join(s_dir, f"{safe_name}.json")
    if not os.path.isfile(filepath):
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data: dict[str, object] = json.load(f)
        msg_count = len(cast("list[object]", data.get("messages", [])))
        logger.info("Session loaded: name=%s, messages=%d, mode=%s", safe_name, msg_count, data.get("mode", "?"))
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load session %s: %s", safe_name, exc)
        return None


def list_sessions(working_directory: str) -> list[dict[str, object]]:
    """List all saved sessions with metadata. Returns list of dicts sorted by save time (newest first)."""
    s_dir = _sessions_dir(working_directory)
    if not os.path.isdir(s_dir):
        return []

    sessions: list[dict[str, object]] = []
    for fname in os.listdir(s_dir):
        if not fname.endswith(".json"):
            continue
        filepath = os.path.join(s_dir, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data: dict[str, object] = json.load(f)
            sessions.append({
                "name": data.get("name", fname[:-5]),
                "saved_at": data.get("saved_at", "unknown"),
                "mode": data.get("mode", "unknown"),
                "model": data.get("model", "unknown"),
                "message_count": len(cast("list[object]", data.get("messages", []))),
                "filepath": filepath,
            })
        except (json.JSONDecodeError, OSError):
            continue

    # Sort newest first
    sessions.sort(key=lambda s: s.get("saved_at", ""), reverse=True)  # type: ignore[arg-type, return-value]
    logger.debug("Listed %d sessions from %s", len(sessions), s_dir)
    return sessions


def delete_session(name: str, working_directory: str) -> bool:
    """Delete a saved session by name. Returns True if successful."""
    s_dir = _sessions_dir(working_directory)
    safe_name = name.strip().replace(" ", "-")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_.")
    filepath = os.path.join(s_dir, f"{safe_name}.json")
    if os.path.isfile(filepath):
        os.remove(filepath)
        logger.info("Session deleted: %s", safe_name)
        return True
    logger.warning("Session not found for deletion: %s", safe_name)
    return False
