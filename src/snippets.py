"""Snippet manager for storing and retrieving reusable code snippets."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

# Snippets directory (inside project root or configurable)
SNIPPETS_DIR = Path("snippets")


def _ensure_dir() -> Path:
    """Ensure snippets directory exists and return its path."""
    snippets_dir = SNIPPETS_DIR.resolve()
    snippets_dir.mkdir(parents=True, exist_ok=True)
    return snippets_dir


def list_snippets() -> list[dict[str, Any]]:
    """Return a list of all saved snippets with metadata."""
    snippets_dir = _ensure_dir()
    snippets: list[dict[str, Any]] = []
    for f in snippets_dir.iterdir():
        if f.suffix == ".snippet":
            try:
                content = f.read_text(encoding="utf-8")
                # First line is the description if it starts with #
                lines = content.split("\n")
                description = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else ""
                snippets.append({
                    "name": f.stem,
                    "description": description,
                    "size": len(content),
                    "language": f.suffix.lstrip("."),
                })
            except Exception as e:
                logger.debug("Error reading snippet %s: %s", f.name, e)
    return sorted(snippets, key=lambda s: s["name"])


def load_snippet(name: str) -> str | None:
    """Load a snippet by name. Returns content or None if not found."""
    snippets_dir = _ensure_dir()
    path = snippets_dir / f"{name}.snippet"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Error loading snippet '%s': %s", name, e)
        return None


def save_snippet(name: str, content: str) -> bool:
    """Save a snippet. Returns True on success."""
    if not name or not name.strip():
        return False
    snippets_dir = _ensure_dir()
    path = snippets_dir / f"{name.strip()}.snippet"
    try:
        path.write_text(content, encoding="utf-8")
        logger.info("Saved snippet: %s", name)
        return True
    except Exception as e:
        logger.error("Error saving snippet '%s': %s", name, e)
        return False


def delete_snippet(name: str) -> bool:
    """Delete a snippet. Returns True on success."""
    snippets_dir = _ensure_dir()
    path = snippets_dir / f"{name}.snippet"
    if not path.exists():
        return False
    try:
        path.unlink()
        logger.info("Deleted snippet: %s", name)
        return True
    except Exception as e:
        logger.error("Error deleting snippet '%s': %s", name, e)
        return False
