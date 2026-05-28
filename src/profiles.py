"""Configuration profiles for the Coding Agent.

Allows saving and loading configuration presets (model, max_tokens,
temperature, top_p, system prompt overrides, and custom persona).
Profiles are stored as JSON files in the profiles/ directory.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

PROFILES_DIR = "profiles"


@dataclass
class Profile:
    """Represents a saved configuration profile."""

    name: str
    model: str = ""
    max_tokens: int = 0
    temperature: float = 0.0
    top_p: float = 0.0
    system_prompt: str = ""
    custom_persona: str = ""


def _ensure_profiles_dir(working_directory: str) -> Path:
    """Ensure the profiles/ directory exists."""
    profiles_dir = Path(working_directory) / PROFILES_DIR
    profiles_dir.mkdir(parents=True, exist_ok=True)
    return profiles_dir


def save_profile(name: str, profile_data: dict[str, Any], working_directory: str) -> str:
    """Save a profile as a JSON file. Returns the file path."""
    safe_name = "".join(c for c in name.strip() if c.isalnum() or c in "-_.")
    if not safe_name:
        safe_name = "custom-profile"
    profiles_dir = _ensure_profiles_dir(working_directory)
    filepath = profiles_dir / f"{safe_name}.json"
    # Only store non-default values
    data: dict[str, Any] = {"name": safe_name}
    for key in ("model", "max_tokens", "temperature", "top_p", "system_prompt", "custom_persona"):
        val = profile_data.get(key)
        if val is not None and val != "" and val != 0 and val != 0.0:
            data[key] = val
    filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Profile saved: name=%s, file=%s", safe_name, filepath)
    return str(filepath)


def load_profile(name: str, working_directory: str) -> Profile | None:
    """Load a profile by name from the profiles/ directory."""
    profiles_dir = _ensure_profiles_dir(working_directory)
    safe_name = "".join(c for c in name.strip() if c.isalnum() or c in "-_.")
    filepath = profiles_dir / f"{safe_name}.json"
    if not filepath.is_file():
        return None
    try:
        data: dict[str, Any] = json.loads(filepath.read_text(encoding="utf-8"))
        return Profile(
            name=data.get("name", safe_name),
            model=str(data.get("model", "")),
            max_tokens=int(data.get("max_tokens", 0)),
            temperature=float(data.get("temperature", 0.0)),
            top_p=float(data.get("top_p", 0.0)),
            system_prompt=str(data.get("system_prompt", "")),
            custom_persona=str(data.get("custom_persona", "")),
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to load profile %s: %s", safe_name, exc)
        return None


def list_profiles(working_directory: str) -> list[Profile]:
    """List all saved profiles in the profiles/ directory."""
    profiles_dir = _ensure_profiles_dir(working_directory)
    result: list[Profile] = []
    if not profiles_dir.is_dir():
        return result
    for f in sorted(profiles_dir.iterdir()):
        if f.suffix != ".json":
            continue
        profile = load_profile(f.stem, working_directory)
        if profile is not None:
            result.append(profile)
    return result


def delete_profile(name: str, working_directory: str) -> bool:
    """Delete a profile by name. Returns True if deleted, False if not found."""
    profiles_dir = _ensure_profiles_dir(working_directory)
    safe_name = "".join(c for c in name.strip() if c.isalnum() or c in "-_.")
    filepath = profiles_dir / f"{safe_name}.json"
    if not filepath.is_file():
        return False
    filepath.unlink()
    logger.info("Profile deleted: name=%s", safe_name)
    return True
